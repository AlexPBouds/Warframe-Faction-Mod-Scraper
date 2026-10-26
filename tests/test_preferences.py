from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ui.preferences import (
    load_preferences,
    normalize_column_order,
    normalize_hidden_columns,
    save_preferences,
)


class NormalizeColumnOrderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.defaults = ("item", "kind", "price", "low")

    def test_saved_order_is_respected(self) -> None:
        self.assertEqual(
            normalize_column_order(self.defaults, ["price", "item", "low", "kind"]),
            ("item", "price", "low", "kind"),
        )

    def test_missing_and_unknown_columns_are_appended(self) -> None:
        self.assertEqual(
            normalize_column_order(self.defaults, ["low", "missing"]),
            ("item", "low", "kind", "price"),
        )

    def test_invalid_saved_value_uses_defaults(self) -> None:
        self.assertEqual(normalize_column_order(self.defaults, None), self.defaults)


class NormalizeHiddenColumnsTests(unittest.TestCase):
    def test_only_hideable_columns_are_kept(self) -> None:
        self.assertEqual(
            normalize_hidden_columns(
                ("item", "kind", "price", "low"),
                ["item", "price", "missing", "price"],
            ),
            ("price",),
        )

    def test_invalid_saved_value_hides_nothing(self) -> None:
        self.assertEqual(
            normalize_hidden_columns(("item", "kind", "price"), "price"), ()
        )


class PreferencesFileTests(unittest.TestCase):
    def test_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "preferences.json"
            save_preferences({"listing_columns": ["item", "price"]}, path)
            self.assertEqual(
                load_preferences(path),
                {"listing_columns": ["item", "price"]},
            )

    def test_invalid_file_uses_empty_preferences(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "preferences.json"
            path.write_text("not json", encoding="utf-8")
            self.assertEqual(load_preferences(path), {})


if __name__ == "__main__":
    unittest.main()
