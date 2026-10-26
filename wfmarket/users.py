from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Iterable

from wfmarket.analysis import ModAnalysis
from wfmarket.syndicates import item_kind, item_name, item_tags

LISTING_TAGS = frozenset({"mod", "augment", "arcane_enhancement"})


@dataclass(frozen=True)
class UserListing:
    order_id: str
    item_id: str
    slug: str
    name: str
    kind: str
    max_rank: int
    rank: int
    quantity: int
    platinum: int
    updated_at: str | None

    @property
    def url(self) -> str:
        return f"https://warframe.market/items/{self.slug}"

    @property
    def rank_label(self) -> str:
        if self.max_rank > 0 and self.rank == self.max_rank:
            return f"Max ({self.rank})"
        return f"Rank {self.rank}"


@dataclass(frozen=True)
class ListingComparison:
    market_low: int | None = None
    sale_price: float | None = None
    delta_low: int | None = None
    delta_sale: float | None = None


def profile_slug(value: str) -> str:
    text = value.strip()
    marker = "/profile/"
    if marker in text:
        text = text.split(marker, 1)[1].split("/", 1)[0].split("?", 1)[0]

    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii").casefold()
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")


def build_user_listings(
    orders: Iterable[dict[str, Any]],
    items: Iterable[dict[str, Any]],
) -> list[UserListing]:
    items_by_id = {
        str(item.get("id")): item for item in items if item.get("id") is not None
    }
    listings: list[UserListing] = []

    for order in orders:
        if not isinstance(order, dict):
            continue
        if str(order.get("type") or "").lower() != "sell":
            continue
        if order.get("visible") is False:
            continue

        item = items_by_id.get(str(order.get("itemId") or ""))
        if item is None:
            continue
        tags = item_tags(item)
        if not any(tag in LISTING_TAGS for tag in tags):
            continue

        platinum = _as_int(order.get("platinum"), 0)
        if platinum <= 0:
            continue

        max_rank = max(0, _as_int(item.get("maxRank"), 0))
        rank = max(0, _as_int(order.get("rank"), 0))
        listings.append(
            UserListing(
                order_id=str(order.get("id") or ""),
                item_id=str(item.get("id") or ""),
                slug=str(item.get("slug") or ""),
                name=item_name(item),
                kind=item_kind(item),
                max_rank=max_rank,
                rank=rank,
                quantity=max(1, _as_int(order.get("quantity"), 1)),
                platinum=platinum,
                updated_at=(
                    str(order.get("updatedAt")) if order.get("updatedAt") else None
                ),
            )
        )

    listings.sort(
        key=lambda listing: (
            listing.name.casefold(),
            listing.rank,
            listing.platinum,
            listing.order_id,
        )
    )
    return listings


def compare_user_listing(
    listing: UserListing,
    analysis: ModAnalysis | None,
    user_name: str,
) -> ListingComparison:
    if analysis is None:
        return ListingComparison()
    if listing.slug != analysis.slug or listing.rank != analysis.target_rank:
        return ListingComparison()

    own_name = user_name.casefold()
    market_low = next(
        (
            offer.platinum
            for offer in analysis.sellers
            if offer.seller.casefold() != own_name
        ),
        None,
    )
    sale_price = analysis.sale_price
    return ListingComparison(
        market_low=market_low,
        sale_price=sale_price,
        delta_low=(listing.platinum - market_low if market_low is not None else None),
        delta_sale=(listing.platinum - sale_price if sale_price is not None else None),
    )


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
