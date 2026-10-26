from __future__ import annotations

import unittest

from wfmarket.analysis import ModAnalysis, SellerOffer
from wfmarket.users import (
    UserListing,
    build_user_listings,
    compare_user_listing,
    profile_slug,
)


def item(
    item_id: int,
    slug: str,
    name: str,
    tags: list[str],
    *,
    max_rank: int = 0,
) -> dict:
    return {
        "id": item_id,
        "slug": slug,
        "maxRank": max_rank,
        "tags": tags,
        "i18n": {"en": {"name": name}},
    }


def order(
    item_id: int,
    platinum: int,
    *,
    order_type: str = "sell",
    rank: int = 0,
    quantity: int = 1,
    visible: bool = True,
    order_id: str = "o1",
) -> dict:
    return {
        "id": order_id,
        "type": order_type,
        "itemId": item_id,
        "platinum": platinum,
        "rank": rank,
        "quantity": quantity,
        "visible": visible,
        "updatedAt": "2026-10-26T12:00:00Z",
    }


def listing(
    *,
    slug: str = "chromatic_blade",
    rank: int = 0,
    platinum: int = 20,
) -> UserListing:
    return UserListing(
        order_id="o1",
        item_id="1",
        slug=slug,
        name="Chromatic Blade",
        kind="Augment",
        max_rank=3,
        rank=rank,
        quantity=1,
        platinum=platinum,
        updated_at=None,
    )


def seller(name: str, platinum: int) -> SellerOffer:
    return SellerOffer(
        seller=name,
        platinum=platinum,
        quantity=1,
        status="ingame",
        last_seen=None,
        rank=0,
    )


def analysis() -> ModAnalysis:
    return ModAnalysis(
        slug="chromatic_blade",
        name="Chromatic Blade",
        max_rank=3,
        target_rank=0,
        rank_label="Unranked (0)",
        rarity="rare",
        kind="Augment",
        tags=("mod", "augment"),
        sellers=[
            seller("Tenno", 10),
            seller("Alpha", 12),
            seller("Bravo", 15),
        ],
        online_seller_count=3,
        sale_price=18.5,
    )


class ProfileSlugTests(unittest.TestCase):
    def test_accepts_names_and_profile_urls(self) -> None:
        self.assertEqual(profile_slug(" Ray_Selby "), "ray-selby")
        self.assertEqual(
            profile_slug("https://warframe.market/profile/O.O-?tab=orders"),
            "o-o",
        )
        self.assertEqual(
            profile_slug("https://warframe.market/profile/ray-selby/orders"),
            "ray-selby",
        )

    def test_strips_names_without_alphanumerics(self) -> None:
        self.assertEqual(profile_slug("!!!"), "")


class BuildUserListingsTests(unittest.TestCase):
    def test_filters_orders_and_maps_catalog_items(self) -> None:
        items = [
            item(
                1,
                "chromatic_blade",
                "Chromatic Blade",
                ["mod", "augment"],
                max_rank=3,
            ),
            item(
                2,
                "arcane_velocity",
                "Arcane Velocity",
                ["arcane_enhancement"],
                max_rank=5,
            ),
            item(3, "ferrite", "Ferrite", ["resource"]),
        ]
        orders = [
            order(1, 20, rank=3, quantity=2, order_id="mod"),
            order(2, 10, quantity=0, order_id="arcane"),
            order(1, 5, order_type="buy", order_id="buy"),
            order(1, 8, visible=False, order_id="hidden"),
            order(3, 4, order_id="resource"),
            order(999, 6, order_id="unknown"),
            order(1, 0, order_id="free"),
        ]

        listings = build_user_listings(orders, items)

        self.assertEqual([entry.order_id for entry in listings], ["arcane", "mod"])
        by_id = {entry.order_id: entry for entry in listings}
        self.assertEqual(by_id["mod"].name, "Chromatic Blade")
        self.assertEqual(by_id["mod"].kind, "Augment")
        self.assertEqual(by_id["mod"].rank, 3)
        self.assertEqual(by_id["mod"].rank_label, "Max (3)")
        self.assertEqual(by_id["mod"].quantity, 2)
        self.assertEqual(by_id["arcane"].kind, "Arcane")
        self.assertEqual(by_id["arcane"].quantity, 1)
        self.assertEqual(by_id["arcane"].rank_label, "Rank 0")


class CompareUserListingTests(unittest.TestCase):
    def test_compares_matching_rank_and_excludes_own_seller(self) -> None:
        comparison = compare_user_listing(listing(), analysis(), "tenno")

        self.assertEqual(comparison.market_low, 12)
        self.assertEqual(comparison.sale_price, 18.5)
        self.assertEqual(comparison.delta_low, 8)
        self.assertEqual(comparison.delta_sale, 1.5)

    def test_returns_empty_when_rank_or_item_does_not_match(self) -> None:
        wrong_rank = compare_user_listing(listing(rank=1), analysis(), "Tenno")
        wrong_item = compare_user_listing(
            listing(slug="other_item"), analysis(), "Tenno"
        )
        missing_analysis = compare_user_listing(listing(), None, "Tenno")

        for comparison in (wrong_rank, wrong_item, missing_analysis):
            self.assertIsNone(comparison.market_low)
            self.assertIsNone(comparison.sale_price)
            self.assertIsNone(comparison.delta_low)
            self.assertIsNone(comparison.delta_sale)

    def test_allows_sale_comparison_when_only_own_listing_exists(self) -> None:
        own_only = analysis()
        own_only.sellers = [seller("Tenno", 10)]
        comparison = compare_user_listing(listing(), own_only, "Tenno")

        self.assertIsNone(comparison.market_low)
        self.assertEqual(comparison.sale_price, 18.5)
        self.assertIsNone(comparison.delta_low)
        self.assertEqual(comparison.delta_sale, 1.5)


if __name__ == "__main__":
    unittest.main()
