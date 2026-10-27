from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

STATUS_LABELS = {
    "ingame": "In-game",
    "online": "Online",
    "offline": "Offline",
}

CONFIDENCE_SMOOTHING = 5.0
FALLBACK_WINDOW_DAYS = 30.0


@dataclass(frozen=True)
class SellerOffer:
    seller: str
    platinum: int
    quantity: int
    status: str
    last_seen: str | None
    rank: int

    @property
    def status_label(self) -> str:
        return STATUS_LABELS.get(self.status, self.status.title() or "Unknown")


@dataclass(frozen=True)
class SalePoint:
    at: datetime
    price: float
    volume: int
    min_price: float
    max_price: float


@dataclass(frozen=True)
class MarketItemData:
    item: dict[str, Any]
    orders: list[dict[str, Any]] | None
    statistics: dict[str, Any] | None


@dataclass
class ModAnalysis:
    slug: str
    name: str
    max_rank: int
    target_rank: int
    rank_label: str
    rarity: str
    kind: str
    tags: tuple[str, ...]

    sellers: list[SellerOffer] = field(default_factory=list)
    all_sellers: list[SellerOffer] = field(default_factory=list)
    online_seller_count: int = 0
    best_buy: int | None = None
    buy_order_count: int = 0

    asking_price: float | None = None
    sale_price: float | None = None
    recent_avg: float | None = None
    last_sale_price: float | None = None
    recent_volume: int = 0
    volume_48h: int = 0
    window_label: str = ""
    window_hours: float = 0.0
    daily_volume: float = 0.0
    velocity: float = 0.0
    confidence: float = 0.0
    score: float = 0.0

    chart_points: list[SalePoint] = field(default_factory=list)
    orders_available: bool = True
    stats_available: bool = True
    warnings: list[str] = field(default_factory=list)

    @property
    def url(self) -> str:
        return f"https://warframe.market/items/{self.slug}"


def analyze_mod(
    item: dict[str, Any],
    orders: list[dict[str, Any]] | None,
    statistics: dict[str, Any] | None,
    *,
    rank_mode: str = "unranked",
    only_ingame: bool = False,
    include_cheaper_ranked: bool = False,
    now: datetime | None = None,
) -> ModAnalysis:
    """Turn raw order-book and completed-sale data into one ranked row.

    ``orders``/``statistics`` may be ``None`` when that request failed. That is
    different from an empty response, which simply means there is no data.
    """

    now = now or datetime.now(timezone.utc)
    max_rank = max(0, _as_int(item.get("maxRank"), 0))
    target_rank = max_rank if rank_mode == "max" else 0
    rank_label = f"Max rank ({target_rank})" if target_rank else "Unranked (0)"
    name = _item_name(item)
    rarity = str(item.get("rarity") or "")
    tags = tuple(str(tag) for tag in (item.get("tags") or ()))

    analysis = ModAnalysis(
        slug=str(item.get("slug") or ""),
        name=name,
        max_rank=max_rank,
        target_rank=target_rank,
        rank_label=rank_label,
        rarity=rarity,
        kind=_item_kind(tags),
        tags=tags,
        orders_available=orders is not None,
        stats_available=statistics is not None,
    )

    # --------------------------------------------------------------- Orders
    orders = orders or []
    unique_sellers, best_buy, buy_count = _extract_orders(
        orders, target_rank, only_ingame, include_cheaper_ranked
    )
    analysis.online_seller_count = len(unique_sellers)
    analysis.all_sellers = list(unique_sellers)
    analysis.sellers = unique_sellers  # Show all sellers
    analysis.best_buy = best_buy
    analysis.buy_order_count = buy_count

    if analysis.sellers:
        # The third-lowest seller is the price needed to appear in the top
        # three listings. It is a realistic "quick sale" asking price.
        index = min(2, len(analysis.sellers) - 1)
        analysis.asking_price = float(analysis.sellers[index].platinum)

    # ----------------------------------------------------------- Statistics
    statistics = statistics or {}
    closed = _closed_statistics(statistics)
    hourly_rows = _filter_statistics(closed.get("48hours") or [], target_rank)
    daily_rows = _filter_statistics(closed.get("90days") or [], target_rank)

    if hourly_rows:
        points = hourly_rows
        window_hours = 48.0
        window_label = "48h"
    else:
        cutoff = now - timedelta(days=FALLBACK_WINDOW_DAYS)
        points = [point for point in daily_rows if point.at >= cutoff]
        window_hours = FALLBACK_WINDOW_DAYS * 24.0
        window_label = "30d"

    analysis.chart_points = points
    analysis.window_hours = window_hours
    analysis.window_label = window_label
    analysis.recent_volume = sum(point.volume for point in points)
    analysis.volume_48h = sum(point.volume for point in hourly_rows)
    analysis.recent_avg = _weighted_price(points)
    analysis.last_sale_price = points[-1].price if points else None

    days = max(window_hours / 24.0, 1.0)
    analysis.daily_volume = analysis.recent_volume / days
    competition = max(analysis.online_seller_count, 1)
    analysis.velocity = analysis.daily_volume / competition
    analysis.confidence = analysis.recent_volume / (
        analysis.recent_volume + CONFIDENCE_SMOOTHING
    )

    # --------------------------------------------------------------- Pricing
    asking = analysis.asking_price
    recent = analysis.recent_avg
    if asking is not None and recent is not None:
        # You can list near the current market, but completed sales define the
        # realistic ceiling. Taking the lower value avoids over-optimistic rows.
        analysis.sale_price = min(asking, recent)
    elif asking is not None:
        analysis.sale_price = asking
    elif recent is not None:
        analysis.sale_price = recent

    # Score = estimated platinum per day available to one seller:
    #     realistic price * (daily sales / online sellers) * sample confidence
    # It intentionally ignores farming/acquisition cost, which the app cannot
    # know. A zero-volume mod always scores zero, no matter how expensive it is.
    if (
        analysis.orders_available
        and analysis.stats_available
        and analysis.recent_volume > 0
        and analysis.sale_price
    ):
        analysis.score = analysis.sale_price * analysis.velocity * analysis.confidence

    # -------------------------------------------------------------- Warnings
    if not analysis.orders_available:
        analysis.warnings.append("Could not load the current order book.")
    if not analysis.stats_available:
        analysis.warnings.append("Could not load completed-sale statistics.")
    if analysis.stats_available and not points:
        analysis.warnings.append(
            "No completed sales at this rank in the last 48 hours or 30 days."
        )
    if analysis.orders_available and not analysis.sellers:
        if only_ingame:
            analysis.warnings.append("No in-game sellers at this rank.")
        else:
            analysis.warnings.append("No online or in-game sellers at this rank.")

    return analysis


def _extract_orders(
    orders: list[dict[str, Any]],
    target_rank: int,
    only_ingame: bool,
    include_cheaper_ranked: bool,
) -> tuple[list[SellerOffer], int | None, int]:
    sellers: dict[str, SellerOffer] = {}
    cheaper_sellers: dict[str, SellerOffer] = {}
    buyers: dict[str, int] = {}

    for order in orders:
        if not isinstance(order, dict):
            continue
        if order.get("visible") is False:
            continue

        order_rank = _as_int(order.get("rank"), 0)
        include_rank = order_rank == target_rank or (
            include_cheaper_ranked and order_rank > target_rank
        )
        if not include_rank:
            continue

        order_type = str(order.get("type") or "").lower()
        user = order.get("user") or {}
        status = str(user.get("status") or "offline").lower()
        if not _status_allowed(status, only_ingame):
            continue

        platinum = _as_int(order.get("platinum"), 0)
        if platinum <= 0:
            continue

        user_key = str(
            user.get("id")
            or user.get("slug")
            or user.get("ingameName")
            or f"unknown-{len(sellers) + len(cheaper_sellers)}"
        )
        seller_name = str(
            user.get("ingameName") or user.get("slug") or "Unknown seller"
        )

        if order_type == "sell":
            offer = SellerOffer(
                seller=seller_name,
                platinum=platinum,
                quantity=max(1, _as_int(order.get("quantity"), 1)),
                status=status,
                last_seen=user.get("lastSeen"),
                rank=order_rank,
            )
            if order_rank == target_rank:
                existing = sellers.get(user_key)
                if existing is None or _offer_sort_key(offer) < _offer_sort_key(
                    existing
                ):
                    sellers[user_key] = offer
            else:
                existing = cheaper_sellers.get(user_key)
                if existing is None or _offer_sort_key(offer) < _offer_sort_key(
                    existing
                ):
                    cheaper_sellers[user_key] = offer
        elif order_type == "buy" and order_rank == target_rank:
            buyers[user_key] = max(buyers.get(user_key, 0), platinum)

    ordered_sellers = sorted(sellers.values(), key=_offer_sort_key)
    if include_cheaper_ranked:
        cutoff = _price_cutoff(ordered_sellers)
        merged = dict(sellers)
        for user_key, offer in cheaper_sellers.items():
            if cutoff is not None and offer.platinum >= cutoff:
                continue
            existing = merged.get(user_key)
            if existing is None or _offer_sort_key(offer) < _offer_sort_key(existing):
                merged[user_key] = offer
        ordered_sellers = sorted(merged.values(), key=_offer_sort_key)

    best_buy = max(buyers.values()) if buyers else None
    return ordered_sellers, best_buy, len(buyers)


def _price_cutoff(sellers: list[SellerOffer]) -> int | None:
    if len(sellers) >= 3:
        return sellers[2].platinum
    if sellers:
        return sellers[-1].platinum
    return None


def _offer_sort_key(offer: SellerOffer) -> tuple[int, int, str]:
    return (offer.platinum, -offer.quantity, offer.seller.casefold())


def _status_allowed(status: str, only_ingame: bool) -> bool:
    if only_ingame:
        return status == "ingame"
    return status in {"ingame", "online"}


def _closed_statistics(statistics: dict[str, Any]) -> dict[str, Any]:
    closed = statistics.get("statistics_closed")
    if isinstance(closed, dict):
        return closed

    payload = statistics.get("payload")
    if isinstance(payload, dict):
        nested = payload.get("statistics_closed")
        if isinstance(nested, dict):
            return nested
    return {}


def _filter_statistics(rows: list[dict[str, Any]], target_rank: int) -> list[SalePoint]:
    points: list[SalePoint] = []

    for row in rows:
        if not isinstance(row, dict):
            continue
        if (
            row.get("mod_rank") is not None
            and _as_int(row.get("mod_rank"), -1) != target_rank
        ):
            continue

        at = _parse_datetime(row.get("datetime"))
        if at is None:
            continue

        price = (
            _as_float(row.get("wa_price"))
            or _as_float(row.get("avg_price"))
            or _as_float(row.get("closed_price"))
            or _as_float(row.get("median"))
        )
        if price <= 0:
            continue

        volume = max(0, _as_int(row.get("volume"), 0))
        points.append(
            SalePoint(
                at=at,
                price=price,
                volume=volume,
                min_price=_as_float(row.get("min_price")) or price,
                max_price=_as_float(row.get("max_price")) or price,
            )
        )

    points.sort(key=lambda point: point.at)
    return points


def _weighted_price(points: list[SalePoint]) -> float | None:
    volume = sum(point.volume for point in points)
    if volume > 0:
        return sum(point.price * point.volume for point in points) / volume
    if points:
        return sum(point.price for point in points) / len(points)
    return None


def _item_name(item: dict[str, Any]) -> str:
    i18n = item.get("i18n") or {}
    localized = i18n.get("en") or {}
    return str(localized.get("name") or item.get("item_name") or item.get("slug") or "")


def _item_kind(tags: tuple[str, ...]) -> str:
    if "arcane_enhancement" in tags:
        return "Arcane"
    if "augment" in tags:
        return "Augment"
    return "Mod"


def _parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
