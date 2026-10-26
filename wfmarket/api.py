from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests

API_V2 = "https://api.warframe.market/v2/"
API_V1 = "https://api.warframe.market/v1/"

USER_AGENT = (
    "PlatScout/1.0 "
    "(desktop market-analysis tool; public Warframe.market API client)"
)
ITEM_CACHE_SECONDS = 6 * 60 * 60


class WFMApiError(RuntimeError):
    """Raised when the Warframe.market API cannot satisfy a request."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


def default_cache_dir() -> Path:
    base = os.getenv("LOCALAPPDATA")
    if base:
        path = Path(base) / "PlatScout" / "cache"
    else:
        path = Path.home() / ".cache" / "plat_scout"

    try:
        path.mkdir(parents=True, exist_ok=True)
        return path
    except OSError:
        fallback = Path.cwd() / ".cache"
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback


class RateLimiter:
    """Reserve request slots so the client stays below a requests/second limit."""

    def __init__(self, requests_per_second: float = 2.8) -> None:
        self._interval = 1.0 / max(requests_per_second, 0.1)
        self._next_slot = 0.0
        self._lock = threading.Lock()

    def wait(self) -> None:
        with self._lock:
            now = time.monotonic()
            delay = self._next_slot - now
            if delay > 0:
                time.sleep(delay)
                now = time.monotonic()
            self._next_slot = max(now, self._next_slot) + self._interval


_SHARED_LIMITER = RateLimiter(2.8)


class WFMarketClient:
    """Small, rate-limited client for the public Warframe.market endpoints.

    - v2 items/orders are the current public API.
    - v1 statistics is still the only public source of completed-sale history.
    """

    def __init__(
        self,
        platform: str = "pc",
        language: str = "en",
        cache_dir: Path | None = None,
        requests_per_second: float = 2.8,
        timeout: float = 25.0,
        limiter: RateLimiter | None = None,
    ) -> None:
        self.platform = platform.lower()
        self.language = language.lower()
        self.cache_dir = cache_dir or default_cache_dir()
        self.timeout = timeout
        self.notes: list[str] = []
        self._limiter = limiter or (
            _SHARED_LIMITER
            if requests_per_second == 2.8
            else RateLimiter(requests_per_second)
        )
        self._session = requests.Session()
        self._session.headers.update(
            {
                "Accept": "application/json",
                "User-Agent": USER_AGENT,
                "Language": self.language,
                "Platform": self.platform,
            }
        )

    def close(self) -> None:
        self._session.close()

    # ------------------------------------------------------------------ HTTP
    def _get_json(self, url: str) -> Any:
        attempts = 3
        last_error: Exception | None = None

        for attempt in range(1, attempts + 1):
            self._limiter.wait()
            try:
                response = self._session.get(url, timeout=self.timeout)
            except requests.RequestException as exc:
                last_error = exc
                if attempt == attempts:
                    break
                time.sleep(min(2 ** (attempt - 1), 6))
                continue

            if response.status_code == 200:
                try:
                    return response.json()
                except ValueError as exc:
                    raise WFMApiError(
                        f"The API returned non-JSON content for {url}"
                    ) from exc

            if response.status_code in (429, 509):
                last_error = WFMApiError(
                    f"Rate limited by Warframe.market (HTTP {response.status_code})",
                    response.status_code,
                )
                if attempt == attempts:
                    break
                delay = self._retry_delay(response, attempt)
                time.sleep(delay)
                continue

            if 500 <= response.status_code < 600 and attempt < attempts:
                last_error = WFMApiError(
                    f"Warframe.market server error (HTTP {response.status_code})",
                    response.status_code,
                )
                time.sleep(min(2 ** (attempt - 1), 6))
                continue

            snippet = " ".join(response.text[:220].split())
            raise WFMApiError(
                f"HTTP {response.status_code} from {url}: {snippet}",
                response.status_code,
            )

        if isinstance(last_error, WFMApiError):
            raise last_error
        raise WFMApiError(f"Could not reach Warframe.market: {last_error}")

    @staticmethod
    def _retry_delay(response: requests.Response, attempt: int) -> float:
        retry_after = response.headers.get("Retry-After")
        if retry_after:
            try:
                return min(max(float(retry_after), 0.5), 15.0)
            except ValueError:
                pass
        return min(2 ** (attempt - 1), 8.0)

    # --------------------------------------------------------------- Catalog
    def get_items(self, force_refresh: bool = False) -> list[dict[str, Any]]:
        """Return the full tradable-item catalog, using a six-hour disk cache."""

        cache_path = self._cache_path()
        if not force_refresh:
            cached = self._load_cache(cache_path, max_age=ITEM_CACHE_SECONDS)
            if cached is not None:
                return cached

        try:
            data = self._get_json(API_V2 + "items")
            items = data.get("data") if isinstance(data, dict) else None
            if not isinstance(items, list):
                raise WFMApiError("The item catalog response had an unexpected shape.")
            self._write_cache(cache_path, items)
            return items
        except (WFMApiError, OSError) as exc:
            stale = self._load_cache(cache_path, max_age=None)
            if stale is not None:
                self.notes.append(
                    "Could not refresh the item catalog; using the cached copy. "
                    f"({exc})"
                )
                return stale
            raise

    def _cache_path(self) -> Path:
        safe_platform = "".join(
            char for char in self.platform if char.isalnum() or char in "-_"
        )
        safe_language = "".join(
            char for char in self.language if char.isalnum() or char in "-_"
        )
        return self.cache_dir / f"items_{safe_platform}_{safe_language}.json"

    @staticmethod
    def _load_cache(path: Path, max_age: float | None) -> list[dict[str, Any]] | None:
        try:
            if not path.exists():
                return None
            if max_age is not None and time.time() - path.stat().st_mtime > max_age:
                return None
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return data
        except (OSError, ValueError):
            return None
        return None

    @staticmethod
    def _write_cache(path: Path, items: list[dict[str, Any]]) -> None:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_name(
                f"{path.name}.{os.getpid()}.{threading.get_ident()}.tmp"
            )
            temporary.write_text(
                json.dumps(items, ensure_ascii=False, separators=(",", ":")),
                encoding="utf-8",
            )
            temporary.replace(path)
        except OSError:
            # A cache failure must never stop the actual market request.
            pass

    # ---------------------------------------------------------------- Orders
    def get_orders(self, slug: str) -> list[dict[str, Any]]:
        """Return visible buy/sell orders for one item."""

        url = API_V2 + "orders/item/" + quote(slug)
        data = self._get_json(url)
        orders = data.get("data") if isinstance(data, dict) else None
        if orders is None:
            return []
        if not isinstance(orders, list):
            raise WFMApiError(f"Unexpected order response for {slug}.")
        return orders

    def get_user_profile(self, slug: str) -> dict[str, Any]:
        """Return the public profile for one Warframe.market user slug."""

        url = API_V2 + "user/" + quote(slug)
        data = self._get_json(url)
        profile = data.get("data") if isinstance(data, dict) else None
        if not isinstance(profile, dict):
            raise WFMApiError(f"Unexpected profile response for {slug}.")
        return profile

    def get_user_orders(self, slug: str) -> list[dict[str, Any]]:
        """Return the public visible orders for one Warframe.market user slug."""

        url = API_V2 + "orders/user/" + quote(slug)
        data = self._get_json(url)
        orders = data.get("data") if isinstance(data, dict) else None
        if orders is None:
            return []
        if not isinstance(orders, list):
            raise WFMApiError(f"Unexpected user-order response for {slug}.")
        return orders

    # ------------------------------------------------------------ Statistics
    def get_statistics(self, slug: str) -> dict[str, Any]:
        """Return the completed-sale statistics payload for one item.

        Warframe.market's v2 API does not expose statistics yet, so this uses
        the still-functional legacy v1 statistics route.
        """

        url = API_V1 + "items/" + quote(slug) + "/statistics"
        data = self._get_json(url)
        payload = data.get("payload") if isinstance(data, dict) else None
        if not isinstance(payload, dict):
            raise WFMApiError(f"Unexpected statistics response for {slug}.")
        return payload
