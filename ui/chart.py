from __future__ import annotations

import tkinter as tk

import customtkinter as ctk
import matplotlib.dates as mdates
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

from ui.theme import (
    ACCENT,
    BORDER,
    CHART_AXES,
    CHART_BG,
    MUTED,
    PANEL,
    TEXT,
    VOLUME,
)
from wfmarket.analysis import ModAnalysis


class SalesChart(ctk.CTkFrame):
    """Embedded matplotlib chart for one item's completed sales."""

    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master, fg_color=PANEL, corner_radius=10)
        self.figure = Figure(figsize=(4.4, 2.2), dpi=100, facecolor=CHART_BG)
        self.canvas = FigureCanvasTkAgg(self.figure, master=self)
        widget = self.canvas.get_tk_widget()
        widget.configure(highlightthickness=0, bd=0, bg=CHART_BG)
        widget.pack(fill="both", expand=True, padx=8, pady=8)
        self.show(None)

    def show(self, analysis: ModAnalysis | None) -> None:
        self.figure.clear()
        axes = self.figure.add_subplot(111)
        axes.set_facecolor(CHART_AXES)

        for spine in axes.spines.values():
            spine.set_color(BORDER)

        if analysis is None:
            self._draw_message(axes, "Select an item to see its recent sales.")
            self.canvas.draw_idle()
            return

        points = analysis.chart_points
        if not points:
            self._draw_message(
                axes,
                "No completed sales at this rank in the last 48 hours or 30 days.",
            )
            self.canvas.draw_idle()
            return

        times = [point.at for point in points]
        prices = [point.price for point in points]
        lows = [point.min_price for point in points]
        highs = [point.max_price for point in points]
        volumes = [point.volume for point in points]

        if len(points) > 1:
            axes.fill_between(times, lows, highs, color=ACCENT, alpha=0.10, linewidth=0)

        axes.plot(
            times,
            prices,
            color=ACCENT,
            linewidth=1.7,
            marker="o",
            markersize=3.8,
            markerfacecolor=ACCENT,
            markeredgewidth=0,
            zorder=3,
        )

        axes.set_ylabel("Platinum", color=MUTED, fontsize=9)
        axes.tick_params(axis="both", colors=MUTED, labelsize=8)
        axes.grid(True, color=BORDER, alpha=0.45, linewidth=0.6, linestyle="--")
        axes.spines["top"].set_visible(False)
        axes.spines["right"].set_visible(False)

        price_floor = min(lows)
        price_ceiling = max(highs)
        padding = max((price_ceiling - price_floor) * 0.15, 1.0)
        axes.set_ylim(max(0, price_floor - padding), price_ceiling + padding)

        # Volume is plotted on a separate axis so cheap, high-volume mods do
        # not flatten the price line.
        volume_axis = axes.twinx()
        volume_axis.set_facecolor("none")
        span_days = max((times[-1] - times[0]).total_seconds() / 86400.0, 0.04)
        bar_width = max(0.02, min(0.75, span_days / max(len(points), 1) * 0.65))
        volume_axis.bar(
            times,
            volumes,
            width=bar_width,
            color=VOLUME,
            alpha=0.24,
            linewidth=0,
            zorder=1,
        )
        volume_axis.set_ylabel("Trades", color=MUTED, fontsize=9)
        volume_axis.tick_params(axis="y", colors=MUTED, labelsize=8)
        volume_axis.set_ylim(0, max(max(volumes) * 1.8, 2))
        volume_axis.spines["top"].set_visible(False)
        volume_axis.spines["left"].set_visible(False)
        volume_axis.spines["right"].set_color(BORDER)

        locator = mdates.AutoDateLocator(minticks=3, maxticks=6)
        axes.xaxis.set_major_locator(locator)
        date_format = "%H:%M" if analysis.window_label == "48h" else "%b %d"
        axes.xaxis.set_major_formatter(mdates.DateFormatter(date_format))
        axes.tick_params(axis="x", rotation=0, pad=5)

        title = (
            f"{analysis.name}  ·  {analysis.rank_label}  ·  "
            f"recent completed sales ({analysis.window_label})"
        )
        axes.set_title(title, color=TEXT, fontsize=10, loc="left", pad=10)

        self.figure.subplots_adjust(left=0.11, right=0.88, top=0.84, bottom=0.18)
        self.canvas.draw_idle()

    def _draw_message(self, axes, message: str) -> None:
        axes.set_axis_off()
        axes.text(
            0.5,
            0.5,
            message,
            transform=axes.transAxes,
            ha="center",
            va="center",
            color=MUTED,
            fontsize=10,
            wrap=True,
        )
