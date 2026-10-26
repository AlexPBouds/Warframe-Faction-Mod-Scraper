from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from wfmarket.analysis import analyze_mod
from wfmarket.syndicates import (
    SYNDICATES_BY_KEY,
    item_kind,
    select_syndicate_items,
)


def order(
    order_type: str,
    platinum: int,
    *,
    rank: int = 0,
    status: str = "ingame",
    user_id: str = "u1",
    name: str = "Tenno",
    quantity: int = 1,
) -> dict:
    return {
        "type": order_type,
        "platinum": platinum,
        "quantity": quantity,
        "rank": rank,
        "visible": True,
        "user": {
            "id": user_id,
            "ingameName": name,
            "status": status,
            "lastSeen": "2026-10-25T12:00:00Z",
        },
    }


def stat(at: datetime, volume: int, price: float, *, rank: int = 0) -> dict:
    return {
        "datetime": at.isoformat(),
        "volume": volume,
        "wa_price": price,
        "avg_price": price,
        "median": price,
        "min_price": price,
        "max_price": price,
        "mod_rank": rank,
    }


ITEM = {
    "slug": "chromatic_blade",
    "maxRank": 3,
    "rarity": "rare",
    "tags": ["mod", "warframe", "excalibur", "augment", "rare"],
    "i18n": {"en": {"name": "Chromatic Blade"}},
}


class AnalysisTests(unittest.TestCase):
    def setUp(self) -> None:
        self.now = datetime(2026, 10, 25, 20, 0, tzinfo=timezone.utc)

    def test_filters_rank_status_and_deduplicates_sellers(self) -> None:
        orders = [
            order("sell", 1, user_id="offline", status="offline"),
            order("sell", 5, user_id="a", name="Alpha"),
            order("sell", 4, user_id="a", name="Alpha"),
            order("sell", 6, user_id="b", name="Bravo", status="online"),
            order("sell", 9, rank=10, user_id="wrong-rank"),
            order("buy", 3, user_id="buyer1"),
            order("buy", 7, user_id="buyer2"),
        ]
        stats = {
            "statistics_closed": {
                "48hours": [
                    stat(self.now - timedelta(hours=2), 2, 10.0),
                    stat(self.now - timedelta(hours=1), 3, 12.0),
                    stat(self.now - timedelta(hours=1), 99, 500.0, rank=10),
                ],
                "90days": [],
            }
        }

        result = analyze_mod(ITEM, orders, stats, rank_mode="unranked", now=self.now)

        self.assertEqual([offer.platinum for offer in result.sellers], [4, 6])
        self.assertEqual(result.online_seller_count, 2)
        self.assertEqual(result.best_buy, 7)
        self.assertEqual(result.recent_volume, 5)
        self.assertEqual(result.volume_48h, 5)
        self.assertAlmostEqual(result.recent_avg, 11.2)
        self.assertGreater(result.score, 0)
        self.assertTrue(result.orders_available)
        self.assertTrue(result.stats_available)
        self.assertEqual(result.sellers[0].seller, "Alpha")

    def test_only_ingame_removes_online_sellers(self) -> None:
        orders = [
            order("sell", 4, user_id="a", status="ingame"),
            order("sell", 5, user_id="b", status="online"),
        ]
        result = analyze_mod(
            ITEM,
            orders,
            {"statistics_closed": {"48hours": [], "90days": []}},
            only_ingame=True,
            now=self.now,
        )
        self.assertEqual(result.online_seller_count, 1)
        self.assertEqual(result.sellers[0].seller, "Tenno")

    def test_zero_volume_scores_zero(self) -> None:
        orders = [order("sell", 100)]
        result = analyze_mod(
            ITEM,
            orders,
            {"statistics_closed": {"48hours": [], "90days": []}},
            now=self.now,
        )
        self.assertEqual(result.score, 0)
        self.assertEqual(result.recent_volume, 0)
        self.assertTrue(result.warnings)

    def test_failed_statistics_never_produces_a_score(self) -> None:
        orders = [order("sell", 100)]
        result = analyze_mod(ITEM, orders, None, now=self.now)
        self.assertEqual(result.score, 0)
        self.assertFalse(result.stats_available)

    def test_max_rank_uses_item_max_rank(self) -> None:
        orders = [
            order("sell", 10, rank=0, user_id="a"),
            order("sell", 100, rank=3, user_id="b"),
        ]
        result = analyze_mod(
            ITEM,
            orders,
            {"statistics_closed": {"48hours": [], "90days": []}},
            rank_mode="max",
            now=self.now,
        )
        self.assertEqual(result.target_rank, 3)
        self.assertEqual(result.asking_price, 100)
        self.assertEqual(result.sellers[0].platinum, 100)

    def test_unranked_can_include_cheaper_ranked_offers(self) -> None:
        orders = [
            order("sell", 10, user_id="a", name="Alpha"),
            order("sell", 12, user_id="b", name="Bravo"),
            order("sell", 15, user_id="c", name="Charlie"),
            order("sell", 8, rank=3, user_id="ranked", name="Ranked"),
        ]
        stats = {
            "statistics_closed": {
                "48hours": [stat(self.now - timedelta(hours=1), 5, 12.0)],
                "90days": [],
            }
        }

        baseline = analyze_mod(ITEM, orders, stats, now=self.now)
        result = analyze_mod(
            ITEM,
            orders,
            stats,
            include_cheaper_ranked=True,
            now=self.now,
        )

        self.assertEqual(baseline.asking_price, 15)
        self.assertEqual(result.asking_price, 12)
        self.assertEqual([offer.platinum for offer in result.sellers], [8, 10, 12])
        self.assertEqual(result.sellers[0].rank, 3)
        self.assertEqual(result.online_seller_count, 4)

    def test_cheaper_ranked_offers_must_beat_the_unranked_cutoff(self) -> None:
        orders = [
            order("sell", 10, user_id="a"),
            order("sell", 12, user_id="b"),
            order("sell", 15, user_id="c"),
            order("sell", 20, rank=3, user_id="ranked"),
        ]
        result = analyze_mod(
            ITEM,
            orders,
            {"statistics_closed": {"48hours": [], "90days": []}},
            include_cheaper_ranked=True,
            now=self.now,
        )
        self.assertEqual([offer.platinum for offer in result.sellers], [10, 12, 15])
        self.assertEqual(result.asking_price, 15)
        self.assertEqual(result.online_seller_count, 3)

    def test_max_rank_does_not_include_lower_ranked_offers(self) -> None:
        orders = [
            order("sell", 5, rank=0, user_id="a"),
            order("sell", 100, rank=3, user_id="b"),
        ]
        result = analyze_mod(
            ITEM,
            orders,
            {"statistics_closed": {"48hours": [], "90days": []}},
            rank_mode="max",
            include_cheaper_ranked=True,
            now=self.now,
        )
        self.assertEqual([offer.platinum for offer in result.sellers], [100])
        self.assertEqual(result.online_seller_count, 1)

    def test_90_day_fallback_uses_only_last_30_days(self) -> None:
        stats = {
            "statistics_closed": {
                "48hours": [],
                "90days": [
                    stat(self.now - timedelta(days=2), 4, 20.0),
                    stat(self.now - timedelta(days=45), 50, 99.0),
                ],
            }
        }
        result = analyze_mod(ITEM, [order("sell", 20)], stats, now=self.now)
        self.assertEqual(result.window_label, "30d")
        self.assertEqual(result.recent_volume, 4)
        self.assertEqual(result.volume_48h, 0)
        self.assertAlmostEqual(result.recent_avg, 20.0)

    def test_syndicate_catalog_selects_mods_and_arcanes(self) -> None:
        items = [
            {
                "slug": "chromatic_blade",
                "tags": ["mod", "augment"],
                "i18n": {"en": {"name": "Chromatic Blade"}},
            },
            {
                "slug": "magus_elevate",
                "tags": ["arcane_enhancement"],
                "i18n": {"en": {"name": "Magus Elevate"}},
            },
            {
                "slug": "primed_bane_of_grineer",
                "tags": ["mod"],
                "i18n": {"en": {"name": "Primed Bane Of Grineer"}},
            },
        ]
        arbiters = SYNDICATES_BY_KEY["arbiters_of_hexis"]
        quills = SYNDICATES_BY_KEY["the_quills"]
        self.assertEqual(
            [item["slug"] for item in select_syndicate_items(items, arbiters)],
            ["chromatic_blade"],
        )
        self.assertEqual(
            [item["slug"] for item in select_syndicate_items(items, quills)],
            ["magus_elevate"],
        )

    def test_item_kind_recognizes_mods_augments_and_arcanes(self) -> None:
        self.assertEqual(item_kind({"tags": ["mod"]}), "Mod")
        self.assertEqual(item_kind({"tags": ["mod", "augment"]}), "Augment")
        self.assertEqual(item_kind({"tags": ["arcane_enhancement"]}), "Arcane")

    def test_analysis_exposes_item_kind(self) -> None:
        result = analyze_mod(
            ITEM,
            [],
            {"statistics_closed": {"48hours": [], "90days": []}},
            now=self.now,
        )
        self.assertEqual(result.kind, "Augment")


if __name__ == "__main__":
    unittest.main()
