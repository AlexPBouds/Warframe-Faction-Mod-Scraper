from __future__ import annotations

import queue
import threading
import time
import tkinter as tk
import webbrowser
from dataclasses import dataclass
from datetime import datetime
from tkinter import ttk
from typing import Any

import customtkinter as ctk

from ui.chart import SalesChart
from ui.frozen_tree import FrozenColumnTree
from ui.preferences import (
    load_preferences,
    normalize_column_order,
    normalize_hidden_columns,
    save_preferences,
)
from ui.theme import (
    ACCENT,
    BAD,
    BG,
    BORDER,
    GOOD,
    MUTED,
    PANEL,
    PANEL_2,
    PANEL_ALT,
    TEXT,
    WARN,
)
from wfmarket.analysis import (
    MarketItemData,
    ModAnalysis,
    SellerOffer,
    analyze_mod,
)
from wfmarket.api import WFMApiError, WFMarketClient
from wfmarket.syndicates import (
    DEFAULT_SYNDICATE,
    SYNDICATES,
    SYNDICATES_BY_LABEL,
    Syndicate,
    item_name,
    select_syndicate_items,
)
from wfmarket.users import (
    UserListing,
    build_user_listings,
    compare_user_listing,
    profile_slug,
)

PLATFORMS = {
    "PC": "pc",
    "PlayStation": "ps4",
    "Xbox": "xbox",
    "Switch": "switch",
    "Mobile": "mobile",
}
PLATFORM_LABELS = {value: label for label, value in PLATFORMS.items()}

RANK_MODES = {
    "Unranked (rank 0)": "unranked",
    "Max rank": "max",
}

TREE_COLUMNS = (
    "item",
    "kind",
    "sale",
    "yours",
    "volume",
    "sellers",
    "low1",
    "low2",
    "low3",
    "avg",
)

TREE_HEADINGS = {
    "item": "Item",
    "kind": "Type",
    "sale": "Est. sale",
    "yours": "Your price",
    "volume": "Sales",
    "sellers": "Sellers",
    "low1": "Lowest #1",
    "low2": "#2",
    "low3": "#3",
    "avg": "Avg sold",
}

TREE_WIDTHS = {
    "item": 170,
    "kind": 70,
    "sale": 84,
    "yours": 100,
    "volume": 100,
    "sellers": 74,
    "low1": 100,
    "low2": 64,
    "low3": 64,
    "avg": 90,
}

LISTING_COLUMNS = ("item", "kind", "rank", "qty", "price", "low", "est", "delta")

LISTING_HEADINGS = {
    "item": "Item",
    "kind": "Type",
    "rank": "Rank",
    "qty": "Qty",
    "price": "Value",
    "low": "Low",
    "est": "Est.",
    "delta": "Δ",
}

LISTING_WIDTHS = {
    "item": 140,
    "kind": 80,
    "rank": 74,
    "qty": 44,
    "price": 60,
    "low": 60,
    "est": 60,
    "delta": 66,
}

TEXT_SORT_COLUMNS = frozenset({"item", "kind"})
LISTING_TEXT_SORT_COLUMNS = frozenset({"item", "kind"})
DEFAULT_SORT_COLUMN = "score"
DEFAULT_LISTING_SORT_COLUMN = "item"
LISTINGS_WIDTH = 650
LISTINGS_MIN_WIDTH = 300
DETAIL_MIN_WIDTH = 370
TABLE_MIN_WIDTH = 360
PANED_SASH_WIDTH = 6
SUMMARY_HELP = (
    "Default order: estimated platinum/day per seller, based on sale price, "
    "completed-sale volume, competition and sales confidence. Click any heading "
    "to sort. Unranked views include cheaper ranked offers; farming cost is not "
    "included. Load your listings to add your lowest matching-rank price."
)
LISTINGS_HELP = (
    "Click a heading to sort. Current syndicate only filters these rows. "
    "Δ low is your price minus the cheapest other seller; negative means you "
    "are cheaper. Comparisons use the loaded table at the matching rank."
)


@dataclass(frozen=True)
class LoadSettings:
    syndicate: Syndicate
    platform: str
    platform_label: str
    rank_mode: str
    rank_label: str
    only_ingame: bool


def price_text(value: float | None) -> str:
    if value is None:
        return "—"
    rounded = round(float(value))
    if abs(float(value) - rounded) < 0.05:
        return f"{int(rounded)}p"
    return f"{float(value):.1f}p"


def signed_price_text(value: float | None) -> str:
    if value is None:
        return "—"
    rounded = round(float(value))
    if rounded == 0:
        return "0p"
    if abs(float(value) - rounded) < 0.05:
        return f"{int(rounded):+d}p"
    return f"{float(value):+.1f}p"


class PlatScoutApp(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.title("Plat Scout")
        self.configure(fg_color=BG)
        self._configure_window_size()

        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self._queue: queue.Queue[tuple[Any, ...]] = queue.Queue()
        self._loading = False
        self._listings_loading = False
        self._closing = False
        self._settings_collapsed = False
        self._panes_ready = False
        self._preferences = load_preferences()
        self._market_columns = normalize_column_order(
            TREE_COLUMNS, self._preferences.get("market_columns")
        )
        self._listing_columns = normalize_column_order(
            LISTING_COLUMNS, self._preferences.get("listing_columns")
        )
        self._market_hidden_columns = normalize_hidden_columns(
            TREE_COLUMNS, self._preferences.get("market_hidden_columns")
        )
        self._listing_hidden_columns = normalize_hidden_columns(
            LISTING_COLUMNS, self._preferences.get("listing_hidden_columns")
        )

        self._raw_items: list[MarketItemData] = []
        self._loaded_syndicate: Syndicate | None = None
        self._loaded_platform: str | None = None
        self._last_warnings: list[str] = []

        self._results: list[ModAnalysis] = []
        self._results_by_slug: dict[str, ModAnalysis] = {}
        self._detail_url: str | None = None
        self._current_analysis: ModAnalysis | None = None
        self._sort_column = DEFAULT_SORT_COLUMN
        self._sort_reverse = True
        self._listing_sort_column = DEFAULT_LISTING_SORT_COLUMN
        self._listing_sort_reverse = False
        self._graph_window: ctk.CTkToplevel | None = None
        self._graph_chart: SalesChart | None = None
        self._columns_menu: tk.Menu | None = None
        self._columns_menu_variables: list[tk.BooleanVar] = []

        self._user_profile: dict[str, Any] | None = None
        self._user_name = ""
        self._user_platform: str | None = None
        self._user_listings: list[UserListing] = []
        self._user_listings_by_slug: dict[str, list[UserListing]] = {}
        self._user_warnings: list[str] = []
        self._listing_syndicate_only_var = ctk.BooleanVar(value=False)

        self._build_header()
        self._build_content()
        self._build_footer()
        self._style_tree()

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(100, self._poll_queue)

    def _configure_window_size(self) -> None:
        try:
            scaling = max(ctk.ScalingTracker.get_window_scaling(self), 1.0)
        except Exception:
            scaling = 1.0

        screen_width = int(self.winfo_screenwidth() / scaling)
        screen_height = int(self.winfo_screenheight() / scaling)
        self._screen_width = screen_width
        self._screen_height = screen_height
        self._minimum_width = min(1080, max(900, screen_width - 20))
        self._minimum_height = min(730, max(560, screen_height - 60))
        width = min(1440, max(self._minimum_width, screen_width - 80))
        height = min(900, max(self._minimum_height, screen_height - 80))

        self.geometry(f"{width}x{height}")
        self.minsize(self._minimum_width, self._minimum_height)
        self.after(250, self._maximize_window)

    def _maximize_window(self) -> None:
        try:
            self.state("zoomed")
            return
        except tk.TclError:
            pass
        try:
            self.attributes("-zoomed", True)
        except tk.TclError:
            pass

    # ------------------------------------------------------------------ UI
    def _build_header(self) -> None:
        header = ctk.CTkFrame(self, fg_color=PANEL, corner_radius=0)
        header.grid(row=0, column=0, sticky="ew")
        header.grid_columnconfigure(0, weight=1)

        title_frame = ctk.CTkFrame(header, fg_color="transparent")
        title_frame.grid(row=0, column=0, sticky="w", padx=(18, 10), pady=(11, 4))

        ctk.CTkLabel(
            title_frame,
            text="PLAT SCOUT",
            font=("Segoe UI", 20, "bold"),
            text_color=TEXT,
        ).pack(anchor="w")

        ctk.CTkLabel(
            title_frame,
            text="Find syndicate mods and arcanes worth selling on Warframe.market.",
            font=("Segoe UI", 10),
            text_color=MUTED,
        ).pack(anchor="w", pady=(1, 0))

        actions = ctk.CTkFrame(header, fg_color="transparent")
        actions.grid(row=0, column=1, sticky="e", padx=(10, 18), pady=(11, 4))

        self.settings_toggle_button = ctk.CTkButton(
            actions,
            text="Filters  ▲",
            command=self._toggle_settings,
            width=104,
            height=34,
            corner_radius=8,
            fg_color=PANEL_2,
            hover_color="#323747",
            text_color=TEXT,
            font=("Segoe UI", 11, "bold"),
        )
        self.settings_toggle_button.grid(row=0, column=0, padx=(0, 8))

        self.refresh_button = ctk.CTkButton(
            actions,
            text="Load market data",
            command=self._start_refresh,
            width=160,
            height=34,
            corner_radius=8,
            fg_color=ACCENT,
            hover_color="#3b83cc",
            text_color=BG,
            text_color_disabled=BG,
            font=("Segoe UI", 11, "bold"),
        )
        self.refresh_button.grid(row=0, column=1)

        self.settings_panel = ctk.CTkFrame(header, fg_color="transparent")
        self.settings_panel.grid(
            row=1, column=0, columnspan=2, sticky="ew", padx=18, pady=(0, 8)
        )
        self.settings_panel.grid_columnconfigure(5, weight=1)

        controls = self.settings_panel
        self.syndicate_menu = self._make_menu(
            controls,
            0,
            "Syndicate",
            [syndicate.label for syndicate in SYNDICATES],
            DEFAULT_SYNDICATE.label,
            width=200,
            command=self._on_market_selection_change,
        )
        self.platform_menu = self._make_menu(
            controls,
            1,
            "Platform",
            list(PLATFORMS),
            "PC",
            width=135,
            command=self._on_market_selection_change,
        )
        self.rank_menu = self._make_menu(
            controls,
            2,
            "Mod rank",
            list(RANK_MODES),
            "Unranked (rank 0)",
            width=165,
            command=self._on_view_filter_change,
        )

        self.only_ingame_var = ctk.BooleanVar(value=False)
        checkbox_frame = ctk.CTkFrame(controls, fg_color="transparent")
        checkbox_frame.grid(row=0, column=3, sticky="w", padx=(4, 0), pady=(17, 0))
        self.only_ingame_check = ctk.CTkCheckBox(
            checkbox_frame,
            text="Only in-game sellers",
            variable=self.only_ingame_var,
            command=self._on_view_filter_change,
            font=("Segoe UI", 11),
            text_color=TEXT,
            checkbox_width=18,
            checkbox_height=18,
            border_width=2,
            fg_color=ACCENT,
            hover_color="#3b83cc",
        )
        self.only_ingame_check.pack(anchor="w")

        min_sales_frame = ctk.CTkFrame(controls, fg_color="transparent")
        min_sales_frame.grid(row=0, column=4, sticky="w", padx=(16, 0))
        ctk.CTkLabel(
            min_sales_frame,
            text="MIN 48H SALES",
            font=("Segoe UI", 9, "bold"),
            text_color=MUTED,
        ).pack(anchor="w")
        self.min_sales_var = ctk.StringVar(value="10")
        self.min_sales_entry = ctk.CTkEntry(
            min_sales_frame,
            textvariable=self.min_sales_var,
            width=82,
            height=32,
            corner_radius=7,
            fg_color=PANEL_2,
            border_color=BORDER,
            text_color=TEXT,
            justify="center",
            font=("Segoe UI", 11),
        )
        self.min_sales_entry.pack(anchor="w", pady=(3, 0))
        self.min_sales_var.trace_add("write", self._on_min_sales_change)

    def _build_listings_panel(self, parent: ctk.CTkFrame) -> None:
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(6, weight=1, minsize=180)

        listings_head = ctk.CTkFrame(parent, fg_color="transparent")
        listings_head.grid(row=0, column=0, sticky="ew", padx=14, pady=(10, 4))
        listings_head.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            listings_head,
            text="My listings",
            font=("Segoe UI", 15, "bold"),
            text_color=TEXT,
            anchor="w",
        ).grid(row=0, column=0, sticky="w")

        self.listings_columns_button = self._make_columns_button(
            listings_head, self._show_listing_columns_menu
        )
        self.listings_columns_button.grid(row=0, column=1, padx=(8, 0))

        ctk.CTkLabel(
            parent,
            text="PROFILE NAME OR URL",
            font=("Segoe UI", 9, "bold"),
            text_color=MUTED,
            anchor="w",
        ).grid(row=1, column=0, sticky="ew", padx=14)

        controls = ctk.CTkFrame(parent, fg_color="transparent")
        controls.grid(row=2, column=0, sticky="ew", padx=12, pady=(3, 0))
        controls.grid_columnconfigure(0, weight=1)

        self.listings_name_var = ctk.StringVar()
        self.listings_name_entry = ctk.CTkEntry(
            controls,
            textvariable=self.listings_name_var,
            placeholder_text="In-game / profile",
            width=190,
            height=32,
            corner_radius=7,
            fg_color=PANEL_2,
            border_color=BORDER,
            text_color=TEXT,
            font=("Segoe UI", 11),
        )
        self.listings_name_entry.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self.listings_name_entry.bind("<Return>", self._on_listings_entry_return)

        self.listings_load_button = ctk.CTkButton(
            controls,
            text="Load",
            command=self._start_listings_load,
            width=92,
            height=32,
            corner_radius=7,
            fg_color=PANEL_2,
            hover_color="#323747",
            text_color=TEXT,
            text_color_disabled=TEXT,
            font=("Segoe UI", 11, "bold"),
        )
        self.listings_load_button.grid(row=0, column=1)

        self.listings_status_label = ctk.CTkLabel(
            parent,
            text="Enter your in-game name or paste your profile URL.",
            font=("Segoe UI", 9),
            text_color=MUTED,
            anchor="w",
            justify="left",
            wraplength=390,
        )
        self.listings_status_label.grid(
            row=3, column=0, sticky="ew", padx=14, pady=(5, 4)
        )

        self.listings_syndicate_only_check = ctk.CTkCheckBox(
            parent,
            text="Current syndicate only",
            variable=self._listing_syndicate_only_var,
            command=self._on_listing_filter_change,
            font=("Segoe UI", 10),
            text_color=TEXT,
            checkbox_width=17,
            checkbox_height=17,
            border_width=2,
            fg_color=ACCENT,
            hover_color="#3b83cc",
        )
        self.listings_syndicate_only_check.grid(
            row=4, column=0, sticky="w", padx=14, pady=(0, 4)
        )

        ctk.CTkLabel(
            parent,
            text=LISTINGS_HELP,
            font=("Segoe UI", 9),
            text_color=MUTED,
            anchor="w",
            justify="left",
            wraplength=390,
        ).grid(row=5, column=0, sticky="ew", padx=14, pady=(0, 6))

        table_frame = ctk.CTkFrame(parent, fg_color="transparent")
        table_frame.grid(row=6, column=0, sticky="nsew", padx=10, pady=(0, 10))
        table_frame.grid_rowconfigure(0, weight=1)
        table_frame.grid_columnconfigure(0, weight=1)

        self.listings_tree = FrozenColumnTree(
            table_frame,
            columns=LISTING_COLUMNS,
            headings=LISTING_HEADINGS,
            widths=LISTING_WIDTHS,
            on_sort=self._sort_listings_by,
            on_select=self._on_listing_select,
            on_double_click=self._on_listing_double_click,
            initial_order=self._listing_columns,
            hidden_columns=self._listing_hidden_columns,
            on_columns_reordered=self._save_listing_columns,
            height=10,
        )
        self.listings_tree.grid(row=0, column=0, sticky="nsew")
        self.listings_tree.tag_configure("odd", background=PANEL_ALT)
        self.listings_tree.tag_configure("even", background="#191c24")
        self._update_listing_headings()

    def _make_menu(
        self,
        parent: ctk.CTkFrame,
        column: int,
        label: str,
        values: list[str],
        initial: str,
        width: int,
        command: Any,
    ) -> ctk.CTkOptionMenu:
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.grid(row=0, column=column, sticky="w", padx=(0, 16))
        ctk.CTkLabel(
            frame,
            text=label.upper(),
            font=("Segoe UI", 9, "bold"),
            text_color=MUTED,
        ).pack(anchor="w")
        menu = ctk.CTkOptionMenu(
            frame,
            values=values,
            command=command,
            width=width,
            height=32,
            corner_radius=7,
            fg_color=PANEL_2,
            button_color=PANEL_2,
            button_hover_color="#323747",
            dropdown_fg_color=PANEL_2,
            dropdown_hover_color="#323747",
            text_color=TEXT,
            dropdown_text_color=TEXT,
            font=("Segoe UI", 11),
            dropdown_font=("Segoe UI", 11),
        )
        menu.set(initial)
        menu.pack(anchor="w", pady=(3, 0))
        return menu

    def _make_columns_button(self, parent: ctk.CTkFrame, command: Any) -> ctk.CTkButton:
        return ctk.CTkButton(
            parent,
            text="Columns  ▾",
            command=command,
            width=92,
            height=26,
            corner_radius=7,
            fg_color=PANEL_2,
            hover_color="#323747",
            text_color=TEXT,
            font=("Segoe UI", 10, "bold"),
        )

    def _build_content(self) -> None:
        content = ctk.CTkFrame(self, fg_color=BG, corner_radius=0)
        content.grid(row=1, column=0, sticky="nsew", padx=14, pady=10)
        content.grid_rowconfigure(0, weight=1)
        content.grid_columnconfigure(0, weight=1)
        self.content = content

        panes = tk.PanedWindow(
            content,
            orient=tk.HORIZONTAL,
            sashwidth=PANED_SASH_WIDTH,
            sashrelief=tk.FLAT,
            sashcursor="sb_h_double_arrow",
            bg=BORDER,
            bd=0,
            relief=tk.FLAT,
            opaqueresize=True,
        )
        panes.grid(row=0, column=0, sticky="nsew")
        self.content_panes = panes

        self._build_left_panel(panes)
        self._build_listings_sidebar(panes)
        self._build_right_panel(panes)
        panes.bind("<Configure>", self._on_content_panes_configure, add="+")

    def _build_listings_sidebar(self, parent: tk.PanedWindow) -> None:
        panel = ctk.CTkFrame(parent, fg_color=PANEL, corner_radius=10)
        parent.add(
            panel,
            minsize=LISTINGS_MIN_WIDTH,
            stretch="never",
            sticky="nsew",
        )
        self.listings_panel = panel
        self._build_listings_panel(panel)

    def _build_left_panel(self, parent: tk.PanedWindow) -> None:
        left = ctk.CTkFrame(parent, fg_color=PANEL, corner_radius=10)
        parent.add(
            left,
            minsize=TABLE_MIN_WIDTH,
            stretch="always",
            sticky="nsew",
        )
        left.grid_columnconfigure(0, weight=1)
        left.grid_rowconfigure(2, weight=1, minsize=160)

        market_head = ctk.CTkFrame(left, fg_color="transparent")
        market_head.grid(row=0, column=0, sticky="ew", padx=14, pady=(10, 1))
        market_head.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            market_head,
            text="Syndicate offerings",
            font=("Segoe UI", 15, "bold"),
            text_color=TEXT,
            anchor="w",
        ).grid(row=0, column=0, sticky="w")

        self.market_columns_button = self._make_columns_button(
            market_head, self._show_market_columns_menu
        )
        self.market_columns_button.grid(row=0, column=1, padx=(8, 0))

        self.summary_subtitle = ctk.CTkLabel(
            left,
            text=SUMMARY_HELP,
            font=("Segoe UI", 9),
            text_color=MUTED,
            anchor="w",
            justify="left",
            wraplength=720,
        )
        self.summary_subtitle.grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 7))

        table_frame = ctk.CTkFrame(left, fg_color="transparent")
        table_frame.grid(row=2, column=0, sticky="nsew", padx=12, pady=(0, 10))
        table_frame.grid_rowconfigure(0, weight=1)
        table_frame.grid_columnconfigure(0, weight=1)

        self.tree = FrozenColumnTree(
            table_frame,
            columns=TREE_COLUMNS,
            headings=TREE_HEADINGS,
            widths=TREE_WIDTHS,
            on_sort=self._sort_by,
            on_select=self._on_tree_select,
            on_double_click=self._on_tree_double_click,
            initial_order=self._market_columns,
            hidden_columns=self._market_hidden_columns,
            on_columns_reordered=self._save_market_columns,
        )
        self.tree.grid(row=0, column=0, sticky="nsew")
        self.tree.tag_configure("odd", background=PANEL_ALT)
        self.tree.tag_configure("even", background="#191c24")
        self._update_headings()
        left.bind("<Configure>", self._on_left_resize, add="+")

    def _build_right_panel(self, parent: tk.PanedWindow) -> None:
        right = ctk.CTkFrame(parent, fg_color=PANEL, corner_radius=10)
        parent.add(
            right,
            minsize=DETAIL_MIN_WIDTH,
            stretch="always",
            sticky="nsew",
        )
        right.grid_columnconfigure(0, weight=1)
        right.grid_rowconfigure(4, weight=1, minsize=250)

        detail_head = ctk.CTkFrame(right, fg_color="transparent")
        detail_head.grid(row=0, column=0, sticky="ew", padx=14, pady=(10, 4))
        detail_head.grid_columnconfigure(0, weight=1)

        title_frame = ctk.CTkFrame(detail_head, fg_color="transparent")
        title_frame.grid(row=0, column=0, sticky="ew")
        title_frame.grid_columnconfigure(0, weight=1)

        self.detail_title = ctk.CTkLabel(
            title_frame,
            text="Select an item",
            font=("Segoe UI", 17, "bold"),
            text_color=TEXT,
            anchor="w",
            justify="left",
            wraplength=400,
        )
        self.detail_title.grid(row=0, column=0, sticky="ew")

        self.detail_subtitle = ctk.CTkLabel(
            title_frame,
            text="Choose a row to inspect its best sellers and recent completed sales.",
            font=("Segoe UI", 9),
            text_color=MUTED,
            anchor="w",
            justify="left",
            wraplength=400,
        )
        self.detail_subtitle.grid(row=1, column=0, sticky="ew", pady=(1, 0))

        self.open_button = ctk.CTkButton(
            detail_head,
            text="Open in browser",
            command=self._open_market_page,
            width=112,
            height=26,
            corner_radius=7,
            fg_color=PANEL_2,
            hover_color="#323747",
            text_color=TEXT,
            font=("Segoe UI", 9),
            state="disabled",
        )
        self.open_button.grid(row=0, column=1, sticky="ne", padx=(8, 0))

        metrics = ctk.CTkFrame(right, fg_color="transparent")
        metrics.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 6))
        for column in range(5):
            metrics.grid_columnconfigure(column, weight=1)

        self.metric_values: dict[str, ctk.CTkLabel] = {}
        metric_specs = [
            ("sale", "EST. SALE", 0),
            ("volume", "SALES", 1),
            ("avg", "AVG SOLD", 2),
            ("sellers", "SELLERS", 3),
            ("buy", "BEST BUY", 4),
        ]
        for key, caption, column in metric_specs:
            card = ctk.CTkFrame(
                metrics,
                fg_color=PANEL_ALT,
                corner_radius=7,
                border_width=1,
                border_color=BORDER,
            )
            card.grid(row=0, column=column, sticky="nsew", padx=2, pady=2)
            value = ctk.CTkLabel(
                card,
                text="—",
                font=("Segoe UI", 14, "bold"),
                text_color=TEXT,
                anchor="w",
            )
            value.pack(anchor="w", padx=8, pady=(6, 0))
            ctk.CTkLabel(
                card,
                text=caption,
                font=("Segoe UI", 8, "bold"),
                text_color=MUTED,
                anchor="w",
            ).pack(anchor="w", padx=8, pady=(0, 6))
            self.metric_values[key] = value

        seller_section = ctk.CTkFrame(right, fg_color="transparent")
        seller_section.grid(row=2, column=0, sticky="ew", padx=14, pady=(2, 4))
        seller_section.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            seller_section,
            text="3 cheapest online / in-game offers",
            font=("Segoe UI", 10, "bold"),
            text_color=TEXT,
            anchor="w",
        ).grid(row=0, column=0, sticky="ew", pady=(0, 3))

        seller_header = ctk.CTkFrame(seller_section, fg_color="transparent")
        seller_header.grid(row=1, column=0, sticky="ew")
        self._seller_grid_columns(seller_header)
        headers = [
            ("Price", 0, 46),
            ("Rank", 1, 30),
            ("Seller", 2, 0),
            ("Status", 3, 54),
            ("Qty", 4, 26),
        ]
        for text, column, width in headers:
            ctk.CTkLabel(
                seller_header,
                text=text.upper(),
                font=("Segoe UI", 8, "bold"),
                text_color=MUTED,
                width=width,
                anchor="w" if column == 2 else "center",
            ).grid(
                row=0,
                column=column,
                sticky="ew" if column == 2 else "",
                padx=(0, 3),
            )

        self.sellers_rows = ctk.CTkFrame(seller_section, fg_color="transparent")
        self.sellers_rows.grid(row=2, column=0, sticky="ew", pady=(1, 0))
        self.sellers_rows.grid_columnconfigure(0, weight=1)
        self._render_seller_placeholder("No item selected.")

        chart_header = ctk.CTkFrame(right, fg_color="transparent")
        chart_header.grid(row=3, column=0, sticky="ew", padx=14, pady=(2, 2))
        chart_header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            chart_header,
            text="SALES HISTORY",
            font=("Segoe UI", 9, "bold"),
            text_color=MUTED,
            anchor="w",
        ).grid(row=0, column=0, sticky="w")

        self.chart_popout_button = ctk.CTkButton(
            chart_header,
            text="Pop out",
            command=self._open_graph_window,
            width=68,
            height=24,
            corner_radius=7,
            fg_color=PANEL_2,
            hover_color="#323747",
            text_color=TEXT,
            text_color_disabled=TEXT,
            font=("Segoe UI", 9),
            state="disabled",
        )
        self.chart_popout_button.grid(row=0, column=1, sticky="e")

        self.chart = SalesChart(right)
        self.chart.grid(row=4, column=0, sticky="nsew", padx=10, pady=(0, 4))

        self.detail_warning = ctk.CTkLabel(
            right,
            text="",
            font=("Segoe UI", 9),
            text_color=WARN,
            anchor="w",
            justify="left",
            wraplength=400,
        )
        self.detail_warning.grid(row=5, column=0, sticky="ew", padx=14, pady=(0, 8))
        right.bind("<Configure>", self._on_right_resize, add="+")

    @staticmethod
    def _seller_grid_columns(frame: ctk.CTkFrame) -> None:
        frame.grid_columnconfigure(0, weight=0, minsize=46)
        frame.grid_columnconfigure(1, weight=0, minsize=30)
        frame.grid_columnconfigure(2, weight=1, minsize=66)
        frame.grid_columnconfigure(3, weight=0, minsize=54)
        frame.grid_columnconfigure(4, weight=0, minsize=26)

    def _build_footer(self) -> None:
        footer = ctk.CTkFrame(self, fg_color=PANEL, corner_radius=0)
        footer.grid(row=2, column=0, sticky="ew")
        footer.grid_columnconfigure(0, weight=1)

        self.status_label = ctk.CTkLabel(
            footer,
            text="Choose a syndicate and platform, then load market data.",
            font=("Segoe UI", 9),
            text_color=MUTED,
            anchor="w",
        )
        self.status_label.grid(row=0, column=0, sticky="ew", padx=(18, 10), pady=7)

        self.progress = ctk.CTkProgressBar(
            footer,
            width=150,
            height=6,
            corner_radius=3,
            fg_color=BORDER,
            progress_color=ACCENT,
        )
        self.progress.grid(row=0, column=1, sticky="e", padx=(6, 10), pady=7)
        self.progress.set(0)

        self.last_updated_label = ctk.CTkLabel(
            footer,
            text="Last updated: —",
            font=("Segoe UI", 9),
            text_color=MUTED,
            anchor="e",
        )
        self.last_updated_label.grid(row=0, column=2, sticky="e", padx=(6, 18), pady=7)

    def _style_tree(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except Exception:
            pass

        style.configure(
            "Market.Treeview",
            background=PANEL_ALT,
            fieldbackground=PANEL_ALT,
            foreground=TEXT,
            borderwidth=0,
            relief="flat",
            rowheight=32,
            font=("Segoe UI", 10),
        )
        style.configure(
            "Market.Treeview.Heading",
            background=PANEL_2,
            foreground=MUTED,
            borderwidth=0,
            relief="flat",
            padding=(4, 8),
            font=("Segoe UI", 9, "bold"),
        )
        style.map(
            "Market.Treeview.Heading",
            background=[("active", PANEL_2)],
            foreground=[("active", TEXT)],
        )
        style.map(
            "Market.Treeview",
            background=[("selected", "#263e5c")],
            foreground=[("selected", TEXT)],
        )
        for scrollbar_style in (
            "Market.Vertical.TScrollbar",
            "Market.Horizontal.TScrollbar",
        ):
            style.configure(
                scrollbar_style,
                background=PANEL_2,
                troughcolor=PANEL_ALT,
                bordercolor=PANEL_ALT,
                arrowcolor=MUTED,
                borderwidth=0,
            )

    def _toggle_settings(self) -> None:
        self._set_settings_collapsed(not self._settings_collapsed)

    def _set_settings_collapsed(self, collapsed: bool) -> None:
        if collapsed == self._settings_collapsed:
            return

        self._settings_collapsed = collapsed
        if collapsed:
            self.settings_panel.grid_remove()
            self.settings_toggle_button.configure(text="Filters  ▼")
        else:
            self.settings_panel.grid()
            self.settings_toggle_button.configure(text="Filters  ▲")

    def _on_content_panes_configure(self, event: Any) -> None:
        if self._panes_ready or event.width <= 1:
            return
        self._panes_ready = True
        self.after_idle(self._set_initial_pane_widths)

    def _set_initial_pane_widths(self) -> None:
        panes = self.content_panes
        total = panes.winfo_width()
        if total <= 1:
            self._panes_ready = False
            return

        sash = int(panes.cget("sashwidth"))
        available = max(0, total - sash * 2)
        listings = min(
            LISTINGS_WIDTH,
            max(LISTINGS_MIN_WIDTH, available - TABLE_MIN_WIDTH - DETAIL_MIN_WIDTH),
        )
        detail = max(
            DETAIL_MIN_WIDTH,
            int((available - listings) * 0.45),
        )
        table = available - listings - detail

        if table < TABLE_MIN_WIDTH:
            deficit = TABLE_MIN_WIDTH - table
            taken = min(deficit, max(0, listings - LISTINGS_MIN_WIDTH))
            listings -= taken
            table += taken
        if table < TABLE_MIN_WIDTH:
            deficit = TABLE_MIN_WIDTH - table
            taken = min(deficit, max(0, detail - DETAIL_MIN_WIDTH))
            detail -= taken
            table += taken

        panes.sash_place(0, table, 0)
        panes.sash_place(1, table + sash + listings, 0)

    def _on_listings_entry_return(self, *_: Any) -> None:
        self._start_listings_load()

    def _on_left_resize(self, event: Any) -> None:
        self.summary_subtitle.configure(wraplength=max(260, event.width - 32))

    def _on_right_resize(self, event: Any) -> None:
        wraplength = max(220, event.width - 42)
        self.detail_title.configure(wraplength=wraplength)
        self.detail_subtitle.configure(wraplength=wraplength)
        self.detail_warning.configure(wraplength=wraplength)

    # --------------------------------------------------------------- Sorting
    def _heading_text(self, column: str) -> str:
        text = TREE_HEADINGS[column]
        if column == self._sort_column:
            arrow = "▼" if self._sort_reverse else "▲"
            return f"{text}  {arrow}"
        return text

    def _update_headings(self) -> None:
        for column in TREE_COLUMNS:
            self.tree.heading(
                column,
                text=self._heading_text(column),
                command=lambda selected=column: self._sort_by(selected),
            )

    def _save_market_columns(self, order: tuple[str, ...]) -> None:
        self._market_columns = order
        self._store_column_order("market_columns", order)

    def _save_listing_columns(self, order: tuple[str, ...]) -> None:
        self._listing_columns = order
        self._store_column_order("listing_columns", order)

    def _store_column_order(self, key: str, order: tuple[str, ...]) -> None:
        self._preferences[key] = list(order)
        save_preferences(self._preferences)

    def _show_market_columns_menu(self) -> None:
        self._show_columns_menu(
            self.market_columns_button,
            self.tree,
            TREE_HEADINGS,
            self._save_market_visibility,
        )

    def _show_listing_columns_menu(self) -> None:
        self._show_columns_menu(
            self.listings_columns_button,
            self.listings_tree,
            LISTING_HEADINGS,
            self._save_listing_visibility,
        )

    def _show_columns_menu(
        self,
        button: ctk.CTkButton,
        tree: FrozenColumnTree,
        headings: dict[str, str],
        on_change: Any,
    ) -> None:
        if self._columns_menu is not None:
            self._columns_menu.destroy()

        menu = tk.Menu(
            self,
            tearoff=False,
            bg=PANEL_2,
            fg=TEXT,
            activebackground="#323747",
            activeforeground=TEXT,
            selectcolor=ACCENT,
            bd=0,
            relief="flat",
            font=("Segoe UI", 10),
        )
        self._columns_menu = menu
        self._columns_menu_variables = []
        hidden = set(tree.hidden_columns)
        for column in tree.column_order[1:]:
            variable = tk.BooleanVar(value=column not in hidden)
            self._columns_menu_variables.append(variable)
            menu.add_checkbutton(
                label=headings[column],
                variable=variable,
                command=lambda selected=column, checked=variable: self._toggle_column(
                    tree, selected, checked, on_change
                ),
            )
        menu.add_separator()
        menu.add_command(
            label="Show all",
            command=lambda: self._show_all_columns(tree, on_change),
        )

        try:
            menu.tk_popup(
                button.winfo_rootx(),
                button.winfo_rooty() + button.winfo_height(),
            )
        finally:
            menu.grab_release()

    def _toggle_column(
        self,
        tree: FrozenColumnTree,
        column: str,
        variable: tk.BooleanVar,
        on_change: Any,
    ) -> None:
        tree.set_column_visible(column, bool(variable.get()))
        on_change()

    def _show_all_columns(self, tree: FrozenColumnTree, on_change: Any) -> None:
        for column in tree.column_order[1:]:
            tree.set_column_visible(column, True)
        on_change()

    def _save_market_visibility(self) -> None:
        self._market_hidden_columns = self.tree.hidden_columns
        self._store_hidden_columns("market_hidden_columns", self._market_hidden_columns)

    def _save_listing_visibility(self) -> None:
        self._listing_hidden_columns = self.listings_tree.hidden_columns
        self._store_hidden_columns(
            "listing_hidden_columns", self._listing_hidden_columns
        )

    def _store_hidden_columns(self, key: str, hidden: tuple[str, ...]) -> None:
        self._preferences[key] = list(hidden)
        save_preferences(self._preferences)

    def _sort_by(self, column: str) -> None:
        if column == self._sort_column:
            self._sort_reverse = not self._sort_reverse
        else:
            self._sort_column = column
            self._sort_reverse = column not in TEXT_SORT_COLUMNS

        self._update_headings()
        self._populate_tree(self._sorted_results())
        self.tree.yview_moveto(0.0)

    def _sort_key(self, analysis: ModAnalysis, column: str) -> Any:
        if column == "item":
            return analysis.name.casefold()
        if column == "kind":
            return analysis.kind.casefold()
        if column == "score":
            return analysis.score
        if column == "sale":
            return analysis.sale_price
        if column == "yours":
            return self._user_price_value(analysis)
        if column == "volume":
            return analysis.recent_volume
        if column == "sellers":
            return analysis.online_seller_count
        if column in ("low1", "low2", "low3"):
            index = int(column[-1]) - 1
            if index < len(analysis.sellers):
                return analysis.sellers[index].platinum
            return None
        if column == "avg":
            return analysis.recent_avg
        return None

    def _sorted_results(self) -> list[ModAnalysis]:
        present: list[tuple[Any, ModAnalysis]] = []
        missing: list[ModAnalysis] = []
        for analysis in self._results:
            value = self._sort_key(analysis, self._sort_column)
            if value is None:
                missing.append(analysis)
            else:
                present.append((value, analysis))

        present.sort(key=lambda pair: pair[0], reverse=self._sort_reverse)
        return [analysis for _, analysis in present] + missing

    # ------------------------------------------------------------- Settings
    def _current_settings(self) -> LoadSettings:
        syndicate = SYNDICATES_BY_LABEL[self.syndicate_menu.get()]
        platform_label = self.platform_menu.get()
        rank_label = self.rank_menu.get()
        return LoadSettings(
            syndicate=syndicate,
            platform=PLATFORMS[platform_label],
            platform_label=platform_label,
            rank_mode=RANK_MODES[rank_label],
            rank_label=rank_label,
            only_ingame=bool(self.only_ingame_var.get()),
        )

    def _on_market_selection_change(self, *_: Any) -> None:
        self._update_refresh_button()
        if self._loading:
            return
        if not self._raw_items:
            self.status_label.configure(
                text="Choose a syndicate and platform, then load market data.",
                text_color=MUTED,
            )
            self._sync_listing_comparisons()
            return
        if not self._selection_matches_loaded():
            self._clear_results()
            self.status_label.configure(
                text="Market selection changed — click Reload market data to fetch it.",
                text_color=MUTED,
            )
            return

        self._rebuild_results()

    def _on_view_filter_change(self, *_: Any) -> None:
        if self._loading or not self._raw_items:
            return
        if not self._selection_matches_loaded():
            self.status_label.configure(
                text="Market selection changed — click Reload market data to fetch it.",
                text_color=MUTED,
            )
            return
        self._rebuild_results()

    def _on_min_sales_change(self, *_: Any) -> None:
        self._on_view_filter_change()

    def _min_sales_threshold(self) -> int:
        try:
            return max(0, int(self.min_sales_var.get().strip()))
        except (TypeError, ValueError):
            return 0

    def _selection_matches_loaded(self) -> bool:
        settings = self._current_settings()
        return (
            self._loaded_syndicate == settings.syndicate
            and self._loaded_platform == settings.platform
        )

    def _update_refresh_button(self) -> None:
        if self._loading:
            return
        if not self._raw_items:
            text = "Load market data"
        elif self._selection_matches_loaded():
            text = "Refresh market data"
        else:
            text = "Reload market data"
        self.refresh_button.configure(state="normal", text=text)

    def _update_listings_button(self) -> None:
        if self._listings_loading:
            return
        self.listings_load_button.configure(state="normal", text="Load listings")

    def _set_result_status(
        self, prefix: str | None = None, *, success: bool = False
    ) -> None:
        total = len(self._raw_items)
        visible = len(self._results)
        threshold = self._min_sales_threshold()
        hidden = max(0, total - visible)
        matches = self._selection_matches_loaded()
        filtered_empty = total > 0 and visible == 0 and threshold > 0

        parts: list[str] = []
        if prefix:
            parts.append(prefix)
        parts.append(f"Showing {visible} of {total} items")
        if threshold:
            parts.append(f"minimum {threshold} sales / 48h")
        if hidden:
            parts.append(f"{hidden} hidden")
        if filtered_empty:
            parts.append("no items meet the minimum")
        if not matches:
            parts.append("market selection changed — reload to fetch it")
        if self._last_warnings:
            parts.append(f"{len(self._last_warnings)} request warning(s)")

        if filtered_empty or not matches or self._last_warnings:
            color = WARN
        elif success and matches:
            color = GOOD
        else:
            color = MUTED
        self.status_label.configure(text=" · ".join(parts), text_color=color)

    # -------------------------------------------------------------- Refresh
    def _start_refresh(self) -> None:
        if self._loading:
            return

        settings = self._current_settings()
        self._loading = True
        self._set_settings_collapsed(True)
        self.refresh_button.configure(state="disabled", text="Loading...")
        self._update_listings_button()
        self.progress.set(0)
        self.status_label.configure(
            text=(
                f"Loading {settings.syndicate.label} offerings from Warframe.market..."
            ),
            text_color=MUTED,
        )

        worker = threading.Thread(
            target=self._fetch_worker, args=(settings,), daemon=True
        )
        worker.start()

    def _fetch_worker(self, settings: LoadSettings) -> None:
        client = WFMarketClient(platform=settings.platform)
        started = time.monotonic()
        try:
            self._queue.put(("status", "Loading item catalog..."))
            items = client.get_items()
            warnings = list(client.notes)

            offerings = select_syndicate_items(items, settings.syndicate)
            if not offerings:
                self._queue.put(
                    (
                        "fatal",
                        (
                            f"No {settings.syndicate.label} mods or arcanes were "
                            "found in the item catalog."
                        ),
                    )
                )
                return

            total = len(offerings)
            results: list[MarketItemData] = []

            for index, item in enumerate(offerings, start=1):
                name = item_name(item)
                slug = str(item.get("slug") or "")
                self._queue.put(("status", f"Loading {name} ({index}/{total})..."))

                orders: list[dict[str, Any]] | None = None
                statistics: dict[str, Any] | None = None

                try:
                    orders = client.get_orders(slug)
                except Exception as exc:
                    warnings.append(f"{name}: order book request failed ({exc})")

                try:
                    statistics = client.get_statistics(slug)
                except Exception as exc:
                    warnings.append(
                        f"{name}: completed-sale statistics request failed ({exc})"
                    )

                results.append(
                    MarketItemData(
                        item=item,
                        orders=orders,
                        statistics=statistics,
                    )
                )
                self._queue.put(("progress", index, total))

            elapsed = time.monotonic() - started
            self._queue.put(("done", settings, results, warnings, elapsed))
        except Exception as exc:
            self._queue.put(("fatal", f"{type(exc).__name__}: {exc}"))
        finally:
            client.close()

    def _start_listings_load(self) -> None:
        if self._listings_loading:
            return

        name = self.listings_name_var.get().strip()
        if not name:
            self.listings_status_label.configure(
                text="Enter your in-game name or Warframe.market profile URL.",
                text_color=BAD,
            )
            self.listings_name_entry.focus_set()
            return

        slug = profile_slug(name)
        if not slug:
            self.listings_status_label.configure(
                text="That name does not contain a usable profile slug.",
                text_color=BAD,
            )
            return

        self._listings_loading = True
        self._user_profile = None
        self._user_name = ""
        self._user_platform = None
        self._user_listings = []
        self._user_listings_by_slug = {}
        self._user_warnings = []
        self._repopulate_current_table()
        self._render_user_listings()
        self.listings_load_button.configure(state="disabled", text="Loading...")
        self._update_refresh_button()
        self.listings_status_label.configure(
            text=f"Looking up {name} on Warframe.market...",
            text_color=MUTED,
        )

        platform = self._current_settings().platform
        worker = threading.Thread(
            target=self._fetch_listings_worker,
            args=(name, slug, platform),
            daemon=True,
        )
        worker.start()

    def _fetch_listings_worker(self, name: str, slug: str, platform: str) -> None:
        client = WFMarketClient(platform=platform)
        try:
            self._queue.put(("user_status", f"Looking up {name}..."))
            try:
                profile = client.get_user_profile(slug)
            except WFMApiError as exc:
                if exc.status_code == 404:
                    self._queue.put(
                        (
                            "user_fatal",
                            (
                                f"No Warframe.market profile found for '{name}'. "
                                "Use the profile name from your Warframe.market URL, "
                                "or paste the full profile URL."
                            ),
                        )
                    )
                else:
                    raise
                return

            actual_slug = str(profile.get("slug") or slug)
            display_name = str(profile.get("ingameName") or name)
            self._queue.put(
                ("user_status", f"Loading sell orders for {display_name}...")
            )
            orders = client.get_user_orders(actual_slug)
            items = client.get_items()
            listings = build_user_listings(orders, items)
            warnings = list(client.notes)
            self._queue.put(("user_done", profile, listings, warnings))
        except Exception as exc:
            self._queue.put(("user_fatal", f"{type(exc).__name__}: {exc}"))
        finally:
            client.close()

    # ----------------------------------------------------------- Queue pump
    def _poll_queue(self) -> None:
        if self._closing:
            return

        try:
            while True:
                message = self._queue.get_nowait()
                kind = message[0]

                if kind == "status":
                    self.status_label.configure(text=message[1], text_color=MUTED)
                elif kind == "progress":
                    current, total = message[1], message[2]
                    self.progress.set(current / total if total else 0)
                elif kind == "done":
                    self._handle_done(message[1], message[2], message[3], message[4])
                elif kind == "fatal":
                    self._handle_fatal(message[1])
                elif kind == "user_status":
                    self.listings_status_label.configure(
                        text=message[1], text_color=MUTED
                    )
                elif kind == "user_done":
                    self._handle_user_done(message[1], message[2], message[3])
                elif kind == "user_fatal":
                    self._handle_user_fatal(message[1])
        except queue.Empty:
            pass

        self.after(100, self._poll_queue)

    def _handle_done(
        self,
        settings: LoadSettings,
        raw_items: list[MarketItemData],
        warnings: list[str],
        elapsed: float,
    ) -> None:
        self._loading = False
        self.progress.set(1)
        self._raw_items = raw_items
        self._loaded_syndicate = settings.syndicate
        self._loaded_platform = settings.platform
        self._last_warnings = list(warnings)

        if self._selection_matches_loaded():
            self._rebuild_results(update_status=False)
            self._set_result_status(
                f"Loaded {len(raw_items)} items in {elapsed:.1f}s", success=True
            )
        else:
            self._clear_results()
            self.status_label.configure(
                text=(
                    f"Loaded {settings.syndicate.label} in {elapsed:.1f}s, but the "
                    "market selection changed — click Reload market data."
                ),
                text_color=WARN,
            )
        self._update_refresh_button()
        self._update_listings_button()
        self.last_updated_label.configure(
            text=f"Last updated: {datetime.now().strftime('%H:%M:%S')}"
        )

    def _handle_fatal(self, message: str) -> None:
        self._loading = False
        self._set_settings_collapsed(False)
        self._update_refresh_button()
        self._update_listings_button()
        self.progress.set(0)
        self.status_label.configure(text=f"Error: {message}", text_color=BAD)

        if not self._results:
            self._clear_detail()

    # -------------------------------------------------------------- Results
    def _clear_results(self) -> None:
        self._results = []
        self._results_by_slug = {}
        self._populate_tree([])
        self._sync_listing_comparisons()

    def _rebuild_results(self, *, update_status: bool = True) -> None:
        settings = self._current_settings()
        threshold = self._min_sales_threshold()
        analyses = [
            analyze_mod(
                data.item,
                data.orders,
                data.statistics,
                rank_mode=settings.rank_mode,
                only_ingame=settings.only_ingame,
                include_cheaper_ranked=settings.rank_mode == "unranked",
            )
            for data in self._raw_items
        ]
        visible = (
            [analysis for analysis in analyses if analysis.volume_48h >= threshold]
            if threshold
            else analyses
        )

        selection = self.tree.selection()
        selected_slug = selection[0] if selection else None
        self._results = visible
        self._results_by_slug = {analysis.slug: analysis for analysis in visible}
        self._populate_tree(self._sorted_results(), selected_slug=selected_slug)

        if update_status:
            self._set_result_status()
        self._sync_listing_comparisons()

    def _populate_tree(
        self, results: list[ModAnalysis], selected_slug: str | None = None
    ) -> None:
        self.tree.delete(*self.tree.get_children())

        for index, analysis in enumerate(results):
            lower_prices = [price_text(offer.platinum) for offer in analysis.sellers]
            while len(lower_prices) < 3:
                lower_prices.append("—")

            values = (
                analysis.name,
                analysis.kind,
                price_text(analysis.sale_price),
                self._user_price_text(analysis),
                f"{analysis.recent_volume} ({analysis.window_label})",
                str(analysis.online_seller_count),
                lower_prices[0],
                lower_prices[1],
                lower_prices[2],
                price_text(analysis.recent_avg),
            )

            tag = "odd" if index % 2 == 0 else "even"

            self.tree.insert(
                "",
                "end",
                iid=analysis.slug,
                values=values,
                tags=(tag,),
            )

        if not results:
            self._clear_detail()
            return

        target = selected_slug if selected_slug in self._results_by_slug else None
        if target is None or not self.tree.exists(target):
            target = results[0].slug

        self.tree.selection_set(target)
        self.tree.focus(target)
        self.tree.see(target)
        analysis = self._results_by_slug.get(target)
        if analysis is not None:
            self._show_detail(analysis)

    def _on_tree_select(self, *_: Any) -> None:
        selection = self.tree.selection()
        if not selection:
            return
        analysis = self._results_by_slug.get(selection[0])
        if analysis is not None:
            self._show_detail(analysis)

    def _on_tree_double_click(self, *_: Any) -> None:
        selection = self.tree.selection()
        if selection:
            analysis = self._results_by_slug.get(selection[0])
            if analysis is not None:
                webbrowser.open(analysis.url)

    def _handle_user_done(
        self,
        profile: dict[str, Any],
        listings: list[UserListing],
        warnings: list[str],
    ) -> None:
        self._listings_loading = False
        self._user_profile = profile
        self._user_name = str(profile.get("ingameName") or profile.get("slug") or "")
        self._user_platform = str(profile.get("platform") or "")
        self._user_listings = listings
        self._user_warnings = list(warnings)
        self._user_listings_by_slug = {}
        for listing in listings:
            self._user_listings_by_slug.setdefault(listing.slug, []).append(listing)

        self._repopulate_current_table()
        self._render_user_listings()
        self._update_listings_status()
        self._update_listings_button()
        self._update_refresh_button()

    def _handle_user_fatal(self, message: str) -> None:
        self._listings_loading = False
        self.listings_status_label.configure(text=f"Error: {message}", text_color=BAD)
        self._update_listings_button()
        self._update_refresh_button()

    def _user_platform_matches(self) -> bool:
        return (
            self._user_platform is not None
            and self._user_platform == self._current_settings().platform
        )

    def _analysis_for_listing(self, listing: UserListing) -> ModAnalysis | None:
        if not self._user_platform_matches():
            return None
        if not self._selection_matches_loaded():
            return None
        return self._results_by_slug.get(listing.slug)

    def _user_price_value(self, analysis: ModAnalysis) -> int | None:
        if self._user_platform is None or not self._user_platform_matches():
            return None
        listings = [
            listing
            for listing in self._user_listings_by_slug.get(analysis.slug, [])
            if listing.rank == analysis.target_rank
        ]
        if not listings:
            return None
        return min(listing.platinum for listing in listings)

    def _user_price_text(self, analysis: ModAnalysis) -> str:
        return price_text(self._user_price_value(analysis))

    def _sync_listing_comparisons(self) -> None:
        if self._user_profile is None:
            return
        self._render_user_listings()
        self._update_listings_status()

    def _listing_heading_text(self, column: str) -> str:
        text = LISTING_HEADINGS[column]
        if column == self._listing_sort_column:
            arrow = "▼" if self._listing_sort_reverse else "▲"
            return f"{text} {arrow}"
        return text

    def _update_listing_headings(self) -> None:
        for column in LISTING_COLUMNS:
            self.listings_tree.heading(
                column,
                text=self._listing_heading_text(column),
                command=lambda selected=column: self._sort_listings_by(selected),
            )

    def _sort_listings_by(self, column: str) -> None:
        if column == self._listing_sort_column:
            self._listing_sort_reverse = not self._listing_sort_reverse
        else:
            self._listing_sort_column = column
            self._listing_sort_reverse = column not in LISTING_TEXT_SORT_COLUMNS

        self._update_listing_headings()
        self._render_user_listings()
        self.listings_tree.yview_moveto(0.0)

    def _listing_sort_key(self, listing: UserListing, column: str) -> Any:
        if column == "item":
            return listing.name.casefold()
        if column == "kind":
            return listing.kind.casefold()
        if column == "rank":
            return listing.rank
        if column == "qty":
            return listing.quantity
        if column == "price":
            return listing.platinum
        comparison = compare_user_listing(
            listing, self._analysis_for_listing(listing), self._user_name
        )
        if column == "low":
            return comparison.market_low
        if column == "est":
            return comparison.sale_price
        if column == "delta":
            return comparison.delta_low
        return None

    def _filtered_user_listings(self) -> list[UserListing]:
        if not self._listing_syndicate_only_var.get():
            return list(self._user_listings)
        slugs = self._current_settings().syndicate.slugs
        return [listing for listing in self._user_listings if listing.slug in slugs]

    def _sorted_user_listings(self) -> list[UserListing]:
        present: list[tuple[Any, UserListing]] = []
        missing: list[UserListing] = []
        for listing in self._filtered_user_listings():
            value = self._listing_sort_key(listing, self._listing_sort_column)
            if value is None:
                missing.append(listing)
            else:
                present.append((value, listing))
        present.sort(key=lambda pair: pair[0], reverse=self._listing_sort_reverse)
        return [listing for _, listing in present] + missing

    def _on_listing_filter_change(self) -> None:
        self._render_user_listings()
        self._update_listings_status()

    def _render_user_listings(self) -> None:
        selection = self.listings_tree.selection()
        selected_id = selection[0] if selection else None
        self.listings_tree.delete(*self.listings_tree.get_children())

        for index, listing in enumerate(self._sorted_user_listings()):
            analysis = self._analysis_for_listing(listing)
            comparison = compare_user_listing(listing, analysis, self._user_name)
            delta = (
                signed_price_text(comparison.delta_low)
                if comparison.market_low is not None
                else "—"
            )
            values = (
                listing.name,
                listing.kind,
                listing.rank_label,
                str(listing.quantity),
                price_text(listing.platinum),
                price_text(comparison.market_low),
                price_text(comparison.sale_price),
                delta,
            )
            tag = "odd" if index % 2 == 0 else "even"
            self.listings_tree.insert(
                "",
                "end",
                iid=listing.order_id,
                values=values,
                tags=(tag,),
            )

        if selected_id is not None and self.listings_tree.exists(selected_id):
            self.listings_tree.selection_set(selected_id)

    def _update_listings_status(self) -> None:
        if self._user_profile is None:
            return

        total = len(self._user_listings)
        filtered = self._filtered_user_listings()
        count = len(filtered)
        if self._listing_syndicate_only_var.get():
            syndicate_label = self._current_settings().syndicate.label
            parts = [
                f"{count} of {total} listings for {self._user_name} in "
                f"{syndicate_label}"
            ]
        else:
            parts = [
                f"{count} listing{'s' if count != 1 else ''} for {self._user_name}"
            ]
        color = MUTED
        if not total:
            parts.append("no visible mod or arcane sell orders")
            color = WARN
        elif not count:
            parts.append("none in the current syndicate")
            color = WARN
        elif not self._user_platform:
            parts.append("profile platform is unavailable; cannot compare prices")
            color = WARN
        elif not self._user_platform_matches():
            profile_platform = PLATFORM_LABELS.get(
                self._user_platform, self._user_platform
            )
            selected_platform = self._current_settings().platform_label
            parts.append(
                f"profile is {profile_platform}; select {profile_platform} to compare "
                f"(current: {selected_platform})"
            )
            color = WARN
        elif not self._raw_items:
            parts.append("load market data to compare prices")
        elif not self._selection_matches_loaded():
            parts.append("reload market data for the current selection to compare")
            color = WARN
        elif not self._results:
            parts.append("no market rows are visible at the current minimum sales")
            color = WARN
        else:
            compared = sum(
                1
                for listing in filtered
                if self._analysis_for_listing(listing) is not None
            )
            parts.append(f"{compared} compared with the loaded table")
            color = GOOD if compared else MUTED

        if self._user_warnings:
            parts.append(f"{len(self._user_warnings)} request warning(s)")
            color = WARN
        self.listings_status_label.configure(text=" · ".join(parts), text_color=color)

    def _on_listing_select(self, *_: Any) -> None:
        selection = self.listings_tree.selection()
        if not selection:
            return
        listing = next(
            (item for item in self._user_listings if item.order_id == selection[0]),
            None,
        )
        if listing is None or self._analysis_for_listing(listing) is None:
            return
        if self.tree.exists(listing.slug):
            self.tree.selection_set(listing.slug)
            self.tree.focus(listing.slug)
            self.tree.see(listing.slug)
            self._on_tree_select()

    def _on_listing_double_click(self, *_: Any) -> None:
        selection = self.listings_tree.selection()
        if not selection:
            return
        listing = next(
            (item for item in self._user_listings if item.order_id == selection[0]),
            None,
        )
        if listing is not None:
            webbrowser.open(listing.url)

    def _repopulate_current_table(self) -> None:
        if not self._results:
            return
        selection = self.tree.selection()
        selected_slug = selection[0] if selection else None
        self._populate_tree(self._sorted_results(), selected_slug=selected_slug)

    # --------------------------------------------------------------- Detail
    def _show_detail(self, analysis: ModAnalysis) -> None:
        subtitle_parts = [analysis.kind, analysis.rank_label]
        if analysis.max_rank:
            subtitle_parts.append(f"max rank {analysis.max_rank}")
        if analysis.rarity:
            subtitle_parts.append(analysis.rarity.title())
        subtitle_parts.append(f"{analysis.online_seller_count} sellers")

        self.detail_title.configure(text=analysis.name)
        self.detail_subtitle.configure(text="  ·  ".join(subtitle_parts))

        self.metric_values["sale"].configure(text=price_text(analysis.sale_price))
        self.metric_values["volume"].configure(
            text=f"{analysis.recent_volume} / {analysis.window_label}"
        )
        self.metric_values["avg"].configure(text=price_text(analysis.recent_avg))
        self.metric_values["sellers"].configure(text=str(analysis.online_seller_count))
        self.metric_values["buy"].configure(text=price_text(analysis.best_buy))

        self._render_sellers(analysis.sellers)

        if analysis.warnings:
            self.detail_warning.configure(
                text="  ·  ".join(analysis.warnings), text_color=WARN
            )
        else:
            self.detail_warning.configure(text="", text_color=WARN)

        self._detail_url = analysis.url
        self._current_analysis = analysis
        self.open_button.configure(state="normal")
        self.chart_popout_button.configure(state="normal")
        self.chart.show(analysis)
        self._refresh_graph_window()

    def _clear_detail(self) -> None:
        self.detail_title.configure(text="Select an item")
        self.detail_subtitle.configure(
            text="Choose a row to inspect its best sellers and recent completed sales."
        )
        for value in self.metric_values.values():
            value.configure(text="—")
        self._render_seller_placeholder("No item selected.")
        self.detail_warning.configure(text="")
        self._detail_url = None
        self._current_analysis = None
        self.open_button.configure(state="disabled")
        self.chart_popout_button.configure(state="disabled")
        self.chart.show(None)
        self._refresh_graph_window()

    def _open_graph_window(self) -> None:
        analysis = self._current_analysis
        if analysis is None:
            return
        if self._graph_window is not None and self._graph_window.winfo_exists():
            if self._graph_chart is not None:
                self._graph_chart.show(analysis)
            self._graph_window.title(f"{analysis.name} — Sales history")
            self._graph_window.deiconify()
            self._graph_window.lift()
            return

        window = ctk.CTkToplevel(self)
        window.title(f"{analysis.name} — Sales history")
        window.configure(fg_color=BG)
        window.transient(self)
        width = min(1000, max(760, self._screen_width - 140))
        height = min(650, max(480, self._screen_height - 140))
        window.geometry(f"{width}x{height}")
        window.minsize(720, 460)
        window.grid_rowconfigure(0, weight=1)
        window.grid_columnconfigure(0, weight=1)

        chart = SalesChart(window)
        chart.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        chart.show(analysis)

        self._graph_window = window
        self._graph_chart = chart
        window.protocol("WM_DELETE_WINDOW", self._close_graph_window)
        window.lift()
        window.focus_force()

    def _close_graph_window(self) -> None:
        if self._graph_window is not None and self._graph_window.winfo_exists():
            self._graph_window.destroy()
        self._graph_window = None
        self._graph_chart = None

    def _refresh_graph_window(self) -> None:
        if self._graph_window is None or not self._graph_window.winfo_exists():
            self._graph_window = None
            self._graph_chart = None
            return
        if self._graph_chart is None:
            return
        analysis = self._current_analysis
        self._graph_chart.show(analysis)
        if analysis is None:
            self._graph_window.title("Sales history")
        else:
            self._graph_window.title(f"{analysis.name} — Sales history")

    def _render_sellers(self, sellers: list[SellerOffer]) -> None:
        for child in self.sellers_rows.winfo_children():
            child.destroy()

        if not sellers:
            self._render_seller_placeholder(
                "No online or in-game sellers at this rank."
            )
            return

        for index, offer in enumerate(sellers, start=1):
            row = ctk.CTkFrame(
                self.sellers_rows,
                fg_color=PANEL_ALT if index % 2 else "transparent",
                corner_radius=6,
            )
            row.grid(row=index - 1, column=0, sticky="ew", pady=2)
            self._seller_grid_columns(row)

            status_color = GOOD if offer.status == "ingame" else ACCENT

            ctk.CTkLabel(
                row,
                text=price_text(offer.platinum),
                font=("Segoe UI", 11, "bold"),
                text_color=TEXT,
                width=46,
                anchor="center",
            ).grid(row=0, column=0, padx=(0, 3), pady=5)

            ctk.CTkLabel(
                row,
                text=str(offer.rank),
                font=("Segoe UI", 9, "bold"),
                text_color=ACCENT if offer.rank > 0 else MUTED,
                width=30,
                anchor="center",
            ).grid(row=0, column=1, padx=(0, 3), pady=5)

            ctk.CTkLabel(
                row,
                text=offer.seller,
                font=("Segoe UI", 10),
                text_color=TEXT,
                anchor="w",
            ).grid(row=0, column=2, sticky="ew", padx=(0, 3), pady=5)

            ctk.CTkLabel(
                row,
                text=offer.status_label,
                font=("Segoe UI", 9, "bold"),
                text_color=status_color,
                width=54,
                anchor="center",
            ).grid(row=0, column=3, padx=(0, 3), pady=5)

            ctk.CTkLabel(
                row,
                text=str(offer.quantity),
                font=("Segoe UI", 10),
                text_color=MUTED,
                width=26,
                anchor="center",
            ).grid(row=0, column=4, padx=(0, 3), pady=5)

    def _render_seller_placeholder(self, text: str) -> None:
        for child in self.sellers_rows.winfo_children():
            child.destroy()
        ctk.CTkLabel(
            self.sellers_rows,
            text=text,
            font=("Segoe UI", 10),
            text_color=MUTED,
            anchor="w",
        ).grid(row=0, column=0, columnspan=5, sticky="ew", padx=4, pady=8)

    def _open_market_page(self) -> None:
        if self._detail_url:
            webbrowser.open(self._detail_url)

    # ---------------------------------------------------------------- Close
    def _on_close(self) -> None:
        self._closing = True
        self.destroy()
