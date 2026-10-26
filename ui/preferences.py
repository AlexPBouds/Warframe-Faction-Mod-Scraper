from __future__ import annotations

import json
import os
from collections.abc import Sequence
from pathlib import Path
from typing import Any

PREFERENCES_FILENAME = "ui_preferences.json"


def default_preferences_path() -> Path:
    base = os.getenv("LOCALAPPDATA")
    if base:
        folder = Path(base) / "WarframeSyndicateMarketScraper"
    else:
        folder = Path.home() / ".config" / "warframe_syndicate_market_scraper"
    return folder / PREFERENCES_FILENAME


def load_preferences(path: Path | None = None) -> dict[str, Any]:
    target = path or default_preferences_path()
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def save_preferences(preferences: dict[str, Any], path: Path | None = None) -> None:
    target = path or default_preferences_path()
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(target.suffix + ".tmp")
        temporary.write_text(
            json.dumps(preferences, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary.replace(target)
    except OSError:
        return


def normalize_column_order(
    default_columns: Sequence[str], saved: Any
) -> tuple[str, ...]:
    defaults = tuple(default_columns)
    if not defaults:
        return ()

    first = defaults[0]
    ordered = [first]
    if isinstance(saved, (list, tuple)):
        for column in saved:
            if isinstance(column, str) and column in defaults and column not in ordered:
                ordered.append(column)

    for column in defaults:
        if column not in ordered:
            ordered.append(column)
    return tuple(ordered)


def normalize_hidden_columns(
    default_columns: Sequence[str], saved: Any
) -> tuple[str, ...]:
    hideable = set(default_columns[1:])
    if not isinstance(saved, (list, tuple)):
        return ()
    hidden: list[str] = []
    for column in saved:
        if isinstance(column, str) and column in hideable and column not in hidden:
            hidden.append(column)
    return tuple(hidden)
