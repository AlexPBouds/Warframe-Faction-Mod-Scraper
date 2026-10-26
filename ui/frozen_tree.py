from __future__ import annotations

import tkinter.font as tkfont
from collections.abc import Callable, Sequence
from tkinter import ttk
from typing import Any

import customtkinter as ctk


class FrozenColumnTree(ctk.CTkFrame):
    def __init__(
        self,
        master: Any,
        *,
        columns: Sequence[str],
        headings: dict[str, str],
        widths: dict[str, int],
        on_sort: Callable[[str], None],
        on_select: Callable[[], None],
        on_double_click: Callable[[], None],
        initial_order: Sequence[str] | None = None,
        hidden_columns: Sequence[str] | None = None,
        on_columns_reordered: Callable[[tuple[str, ...]], None] | None = None,
        style: str = "Market.Treeview",
        selectmode: str = "browse",
        height: int = 10,
    ) -> None:
        super().__init__(master, fg_color="transparent")
        self.columns = tuple(columns)
        self.first_column = self.columns[0]
        self.body_columns = self.columns[1:]
        self._widths = dict(widths)
        self._on_select = on_select
        self._on_double_click = on_double_click
        self._on_columns_reordered = on_columns_reordered
        self._order = self._normalize_order(initial_order)
        self._hidden_columns = {
            column for column in (hidden_columns or ()) if column in self.body_columns
        }
        self._syncing_selection = False
        self._syncing_scroll = False
        self._last_selected: str | None = None
        self._drag_column: str | None = None
        self._drag_start_x = 0
        self._dragging_columns = False
        self._drag_changed = False
        self._font = tkfont.Font(family="Segoe UI", size=10)

        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=0)
        self.grid_columnconfigure(1, weight=1)

        self.frozen = ttk.Treeview(
            self,
            columns=(self.first_column,),
            show="headings",
            style=style,
            selectmode=selectmode,
            height=height,
        )
        self.body = ttk.Treeview(
            self,
            columns=self.body_columns,
            show="headings",
            style=style,
            selectmode=selectmode,
            height=height,
        )

        for column in self.columns:
            target = self.frozen if column == self.first_column else self.body
            target.column(
                column,
                width=self._widths[column],
                minwidth=self._widths[column],
                anchor="w" if column == self.first_column else "center",
                stretch=False,
            )
            target.heading(
                column,
                text=headings[column],
                command=lambda selected=column: self._on_sort(selected),
            )

        self.frozen.grid(row=0, column=0, sticky="nsew")
        self.body.grid(row=0, column=1, sticky="nsew")

        self._vscroll = ttk.Scrollbar(
            self,
            orient="vertical",
            command=self._scroll_y,
            style="Market.Vertical.TScrollbar",
        )
        self._xscroll = ttk.Scrollbar(
            self,
            orient="horizontal",
            command=self.body.xview,
            style="Market.Horizontal.TScrollbar",
        )
        self._vscroll.grid(row=0, column=2, sticky="ns", padx=(4, 0))
        self._xscroll.grid(row=1, column=1, sticky="ew", pady=(4, 0))

        self.body.configure(displaycolumns=self.visible_body_columns)
        self.frozen.configure(yscrollcommand=self._frozen_yscroll)
        self.body.configure(
            yscrollcommand=self._body_yscroll,
            xscrollcommand=self._xscroll.set,
        )
        self.frozen.bind("<<TreeviewSelect>>", self._frozen_selected)
        self.body.bind("<<TreeviewSelect>>", self._body_selected)
        self.frozen.bind("<Double-1>", self._double_clicked)
        self.body.bind("<Double-1>", self._double_clicked)
        self.body.bind("<ButtonPress-1>", self._column_press, add="+")
        self.body.bind("<B1-Motion>", self._column_motion, add="+")
        self.body.bind("<ButtonRelease-1>", self._column_release, add="+")
        self.body.bind("<Configure>", self._resize_columns, add="+")
        self.after_idle(self._resize_columns)

    def insert(
        self,
        parent: str,
        index: Any,
        iid: str | None = None,
        values: Sequence[Any] = (),
        tags: Sequence[str] = (),
    ) -> str:
        row = tuple(values)
        item_text = self._fit_text(str(row[0]) if row else "")
        item_id = self.frozen.insert(
            parent, index, iid=iid, values=(item_text,), tags=tuple(tags)
        )
        try:
            self.body.insert(
                parent, index, iid=item_id, values=row[1:], tags=tuple(tags)
            )
        except Exception:
            self.frozen.delete(item_id)
            raise
        self.after_idle(self._resize_columns)
        return item_id

    def delete(self, *items: str) -> None:
        targets = items or self.get_children()
        self.frozen.delete(*targets)
        self.body.delete(*targets)
        self._last_selected = None
        self.after_idle(self._resize_columns)

    def get_children(self, item: str = "") -> tuple[str, ...]:
        return self.body.get_children(item)

    def exists(self, item: str) -> bool:
        return bool(self.body.exists(item))

    def selection(self) -> tuple[str, ...]:
        return self.body.selection() or self.frozen.selection()

    def selection_set(self, items: str | Sequence[str]) -> None:
        selected = (items,) if isinstance(items, str) else tuple(items)
        self._syncing_selection = True
        try:
            if selected:
                self.frozen.selection_set(*selected)
                self.body.selection_set(*selected)
            else:
                self.frozen.selection_remove(self.frozen.selection())
                self.body.selection_remove(self.body.selection())
        finally:
            self._syncing_selection = False
        self._last_selected = selected[0] if selected else None

    def focus(self, item: str) -> None:
        self.frozen.focus(item)
        self.body.focus(item)

    def see(self, item: str) -> None:
        self.body.see(item)
        self.frozen.see(item)

    @property
    def column_order(self) -> tuple[str, ...]:
        return self._order

    @property
    def hidden_columns(self) -> tuple[str, ...]:
        return tuple(
            column for column in self._order[1:] if column in self._hidden_columns
        )

    @property
    def visible_body_columns(self) -> tuple[str, ...]:
        return tuple(
            column for column in self._order[1:] if column not in self._hidden_columns
        )

    def set_column_order(self, order: Sequence[str]) -> None:
        normalized = self._normalize_order(order)
        if normalized == self._order:
            return
        self._order = normalized
        self.body.configure(displaycolumns=self.visible_body_columns)
        self.after_idle(self._resize_columns)

    def set_column_visible(self, column: str, visible: bool) -> None:
        if column == self.first_column or column not in self.body_columns:
            return
        if visible:
            self._hidden_columns.discard(column)
        else:
            self._hidden_columns.add(column)
        self.body.configure(displaycolumns=self.visible_body_columns)
        self.after_idle(self._resize_columns)

    def heading(self, column: str, **options: Any) -> Any:
        target = self.frozen if column == self.first_column else self.body
        if options:
            target.heading(column, **options)
            return None
        return target.heading(column)

    def column(self, column: str, **options: Any) -> Any:
        target = self.frozen if column == self.first_column else self.body
        if options:
            target.column(column, **options)
            return None
        return target.column(column)

    def tag_configure(self, tag: str, **options: Any) -> None:
        self.frozen.tag_configure(tag, **options)
        self.body.tag_configure(tag, **options)

    def yview_moveto(self, fraction: float) -> None:
        self._syncing_scroll = True
        try:
            self.frozen.yview_moveto(fraction)
            self.body.yview_moveto(fraction)
        finally:
            self._syncing_scroll = False

    def xview_moveto(self, fraction: float) -> None:
        self.body.xview_moveto(fraction)

    def _normalize_order(self, order: Sequence[str] | None) -> tuple[str, ...]:
        ordered = [self.first_column]
        if order:
            for column in order:
                if column in self.body_columns and column not in ordered:
                    ordered.append(column)
        for column in self.body_columns:
            if column not in ordered:
                ordered.append(column)
        return tuple(ordered)

    def _column_press(self, event: Any) -> None:
        self._drag_column = None
        self._dragging_columns = False
        self._drag_changed = False

        if self.body.identify_region(event.x, event.y) != "heading":
            self.body.configure(cursor="")
            return

        display_column = self.body.identify_column(event.x)
        if not display_column:
            return
        try:
            index = int(display_column[1:]) - 1
        except ValueError:
            return

        order = self.visible_body_columns
        if index < 0 or index >= len(order):
            return

        self._drag_column = order[index]
        self._drag_start_x = event.x
        self.body.configure(cursor="fleur")

    def _column_motion(self, event: Any) -> str | None:
        if self._drag_column is None:
            return None
        if not self._dragging_columns:
            if abs(event.x - self._drag_start_x) < 8:
                return None
            self._dragging_columns = True

        display_column = self.body.identify_column(event.x)
        if not display_column:
            return "break"
        try:
            target_index = int(display_column[1:]) - 1
        except ValueError:
            return "break"

        visible_order = self.visible_body_columns
        target_index = max(0, min(target_index, len(visible_order) - 1))
        target_column = visible_order[target_index]
        body_order = list(self._order[1:])
        source_index = body_order.index(self._drag_column)
        target_position = body_order.index(target_column)
        if target_position != source_index:
            body_order.insert(target_position, body_order.pop(source_index))
            self._order = (self.first_column, *body_order)
            self.body.configure(displaycolumns=self.visible_body_columns)
            self._drag_changed = True
        return "break"

    def _column_release(self, _: Any) -> str | None:
        if self._drag_column is None:
            return None

        dragging = self._dragging_columns
        changed = self._drag_changed
        self._drag_column = None
        self._dragging_columns = False
        self._drag_changed = False
        self.body.configure(cursor="")
        self.after_idle(self._resize_columns)

        if not dragging:
            return None
        if changed and self._on_columns_reordered is not None:
            self._on_columns_reordered(self._order)
        return "break"

    def _fit_text(self, text: str) -> str:
        limit = max(12, self._widths[self.first_column] - 12)
        if self._font.measure(text) <= limit:
            return text

        ellipsis = "…"
        available = limit - self._font.measure(ellipsis)
        if available <= 0:
            return ellipsis

        low = 0
        high = len(text)
        while low < high:
            middle = (low + high + 1) // 2
            if self._font.measure(text[:middle].rstrip()) <= available:
                low = middle
            else:
                high = middle - 1
        return f"{text[:low].rstrip()}{ellipsis}"

    def _scroll_y(self, *args: Any) -> None:
        self._syncing_scroll = True
        try:
            self.frozen.yview(*args)
            self.body.yview(*args)
        finally:
            self._syncing_scroll = False

    def _frozen_yscroll(self, first: str, last: str) -> None:
        self._vscroll.set(first, last)
        if self._syncing_scroll:
            return
        self._syncing_scroll = True
        try:
            self.body.yview_moveto(first)
        finally:
            self._syncing_scroll = False

    def _body_yscroll(self, first: str, last: str) -> None:
        self._vscroll.set(first, last)
        if self._syncing_scroll:
            return
        self._syncing_scroll = True
        try:
            self.frozen.yview_moveto(first)
        finally:
            self._syncing_scroll = False

    def _frozen_selected(self, *_: Any) -> None:
        if self._syncing_selection:
            return
        selected = self.frozen.selection()
        self._syncing_selection = True
        try:
            if selected:
                if self.body.selection() != selected:
                    self.body.selection_set(selected[0])
                self.body.focus(selected[0])
                self.body.see(selected[0])
            else:
                self.body.selection_remove(self.body.selection())
        finally:
            self._syncing_selection = False
        self._emit_selection(selected[0] if selected else None)

    def _body_selected(self, *_: Any) -> None:
        if self._syncing_selection:
            return
        selected = self.body.selection()
        self._syncing_selection = True
        try:
            if selected:
                if self.frozen.selection() != selected:
                    self.frozen.selection_set(selected[0])
                self.frozen.focus(selected[0])
                self.frozen.see(selected[0])
            else:
                self.frozen.selection_remove(self.frozen.selection())
        finally:
            self._syncing_selection = False
        self._emit_selection(selected[0] if selected else None)

    def _emit_selection(self, item: str | None) -> None:
        if item == self._last_selected:
            return
        self._last_selected = item
        if item is not None:
            self._on_select()

    def _double_clicked(self, *_: Any) -> None:
        self._on_double_click()

    def _resize_columns(self, *_: Any) -> None:
        visible = self.visible_body_columns
        if not visible:
            self._xscroll.grid_remove()
            self.body.xview_moveto(0)
            return

        available = self.body.winfo_width()
        if available <= 1:
            self.after_idle(self._resize_columns)
            return

        required_width = sum(self._widths[column] for column in visible)
        if available < required_width:
            for column in visible:
                self.body.column(column, width=self._widths[column])
            self._xscroll.grid()
            return

        base_widths = [self._widths[column] for column in visible]
        extra = available - required_width
        share, remainder = divmod(extra, len(visible))
        for index, (column, width) in enumerate(zip(visible, base_widths)):
            width += share
            if index < remainder:
                width += 1
            self.body.column(column, width=width)
        self._xscroll.grid_remove()
        self.body.xview_moveto(0)
