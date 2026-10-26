# Plat Scout

Plat Scout is a small desktop app for finding the best **syndicate mods and
arcanes to sell** on [Warframe.market](https://warframe.market). Pick a syndicate, and the app
fetches the current order books and recent completed-sale statistics for that
syndicate's tradable offerings, then sorts them by realistic selling opportunity
by default. Every column can be re-sorted.

[![Latest release](https://img.shields.io/github/v/release/AlexPBouds/Warframe-Faction-Mod-Scraper?label=Download&sort=semver)](https://github.com/AlexPBouds/Warframe-Faction-Mod-Scraper/releases/latest)

## Download (Windows)

1. Open the [latest release](https://github.com/AlexPBouds/Warframe-Faction-Mod-Scraper/releases/latest).
2. Download `Plat-Scout-vX.Y.Z.exe`.
3. Double-click it. No Python installation is needed.

The executable is unsigned, so Windows SmartScreen may show "Windows protected
your PC". Click **More info**, then **Run anyway** to start it.

Prefer to run from source? See [Quick start (Windows, from source)](#quick-start-windows-from-source).

## What it shows

- Every tradable mod and arcane sold by the selected syndicate.
- A default turnover ranking that balances estimated sale value, completed-sale
  volume and seller competition, with no separate "top opportunity" callout.
- The **estimated platinum sale price** and supporting market data.
- The **three cheapest online or in-game offers**, with a rank column so cheaper
  ranked offers are easy to spot.
- The recent completed-sale volume and volume-weighted average sale price.
- A chart of recent completed sales, with trade volume on a second axis and a
  **Pop out** window for a larger view.
- Clickable column headers that sort ascending or descending. Drag the non-frozen
  headings to reorder columns, and use each table's **Columns** button to show or
  hide them. Visible columns resize automatically, and reordering and visibility
  are saved.
- A collapsible filter bar, with the load/refresh button kept in the top-right.
- A **My listings** sidebar that loads your visible mod and arcane sell orders
  from your Warframe.market profile and compares them with the table.
- Manually resizable table, listing and detail panes, with a frozen **Item**
  column in both tables so names stay visible while scrolling right.
- Sortable, reorderable listing columns and a **Current syndicate only** filter.
- A **Your price** column in the market table and a **Value** column in **My
  listings**, showing your lowest listing at the selected rank.
- Optional "only in-game sellers" filtering.
- A minimum **48h sales** filter, defaulting to `10`.
- Unranked or max-rank pricing. Unranked views also include cheaper ranked
  offers, so a max-rank listing that undercuts the unranked market is visible.
- PC, PlayStation, Xbox, Switch and Mobile marketplaces.
- Manual loading: data is fetched only when you click **Load market data**.
  Changing the rank, in-game or minimum-sales filters re-analyzes the cached
  response instantly without another network refresh.

The three lowest offer columns in the table show prices. Select a row to see
the sellers' prices, ranks, online status and quantities, plus that item's sales
graph. Click a column heading once for the default direction and again to
reverse it.

Use **My listings** to enter your in-game name, profile slug, or full
Warframe.market profile URL and click **Load listings**. The sidebar shows every
visible mod and arcane sell order on that profile, with the **Value** column
showing your price, plus the lowest competing offer, the estimated sale price and
the difference from the lowest offer. Click any listing heading to sort it. Drag
the non-frozen headings to reorder either table, or use **Columns** to hide and
restore them; both settings are saved automatically and restored on the next
launch. **Current syndicate only** hides
listings outside the selected syndicate. Comparisons require the profile's
platform to match the selected platform and the loaded table to contain the same
item at the same rank. Selecting a listing selects its market row; double-clicking
opens its Warframe.market page. Drag the dividers between the three content panes
to resize them. Long item names are shortened with an ellipsis to keep every
column readable.

## Supported syndicates

The six main syndicates sell Warframe and weapon augment mods:

- Arbiters of Hexis
- Cephalon Suda
- Steel Meridian
- The Perrin Sequence
- Red Veil
- New Loka

These additional syndicates add arcanes and other tradable mods:

- The Quills
- Vox Solaris
- Ostron
- Solaris United
- Entrati
- Cavia
- The Hex
- The Holdfasts
- Necraloid
- Conclave (PvP)

The app only shows offerings that are present in the Warframe.market tradable
item catalog, so untradable blueprints and services are skipped.

## Quick start (Windows, from source)

Prefer not to use the prebuilt executable? Double-click `run.bat`.

The first run creates a `.venv` folder, installs the dependencies and then opens
the app. Later runs just launch it. Python 3.10 or newer is required.

## Manual start

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe app.py
```

On macOS/Linux, use the equivalent `python` commands; only `run.bat` is
Windows-specific.

## Build the executable

To build the same single-file Windows executable locally:

```powershell
.\build.ps1
```

The output is `dist\Plat-Scout.exe`. Python 3.10 or newer is required.

Releases are built automatically by
`.github/workflows/release.yml` whenever a tag starting with `v` is pushed. To
publish a new version:

```powershell
git tag v1.0.0
git push origin v1.0.0
```

The workflow attaches the executable to a new GitHub release. You can also run
the workflow manually from the **Actions** tab to produce a downloadable test
artifact.

## How to use it

1. Pick a **Syndicate**. The default is **Arbiters of Hexis**.
2. Pick your **Platform**.
3. Pick **Unranked (rank 0)** or **Max rank** depending on what you plan to sell.
4. Leave **Only in-game sellers** off to include everyone who is online *or*
   in-game, or turn it on to require the `ingame` status.
5. Set **Min 48h sales** (default `10`) to hide items with too little recent
   completed-sale volume.
6. Click **Load market data**. The app fetches orders and statistics for every
   rank of every offering once, then collapses the filters. Changing the rank,
   in-game or minimum-sales filters afterward updates the table immediately
   without another network request. Changing the syndicate or platform clears
   the current table and requires clicking **Reload market data**.
7. Click any row to inspect the three cheapest offers and the recent sales
   graph. Use **Pop out** for a larger resizable chart. Double-click a row to
   open its Warframe.market page.
8. Click a column heading to sort by that column. Click it again to reverse the
   direction. Drag a non-frozen heading to move that column, or use **Columns**
   to hide and restore columns; both choices are saved automatically. Sorting
   jumps back to the top and selects the new first row.
9. In the **My listings** sidebar, enter your in-game name or profile URL and
   click **Load listings**. Sort, reorder or hide the listing table's columns, or
   enable **Current syndicate only** to hide the rest of your orders. Market and
   listing loads can run at the same time, so you can start both without waiting.
   Drag the dividers between the table, listings and detail panes to resize them.
   Click **Load listings** again after changing your orders on Warframe.market.

## How the ranking works

The ranking is deliberately **not** just the highest price. A 300p item with one
sale per month is not a better target than a 30p item that sells dozens of times
per day. The score is internal: the table displays the estimated sale price, not
a platinum-per-day figure.

For every item at the selected rank:

```text
realistic_sale_price = min(third_lowest_online_seller, recent_weighted_average_sale_price)

daily_sales          = completed sales in the window / number of days in the window
sales_per_seller     = daily_sales / number of online or in-game sellers
confidence           = sales_in_window / (sales_in_window + 5)

score = realistic_sale_price * sales_per_seller * confidence
```

When **Unranked** is selected, higher-rank sellers whose offer is cheaper than
the unranked cutoff are included in the seller competition and asking price.
The seller detail panel shows their rank. Completed-sale statistics still use
the selected rank, because a max-rank sale is not an unranked sale.

The **Min 48h sales** filter uses only the `48hours` statistics. Items that have
no 48-hour rows are hidden when the threshold is above zero, even if they have
older 30-day volume.

The result is an internal estimate of **platinum per day available to one
seller**. It drives the default table ordering, but it is not shown as a column
or metric card and there is no separate "top opportunity" callout. A short hint
above the table explains the default order and that every heading is sortable.
The confidence factor pulls down items with very few completed sales, and an
item with zero recent sales always scores zero.

Important: the app does **not** know how long it takes you to earn the standing
or acquire an item, so this is revenue opportunity before farming/acquisition
cost, not accounting profit.

More detail, including worked examples and every code path, is in
[CODE_WALKTHROUGH.md](CODE_WALKTHROUGH.md).

## Data sources

- `GET https://api.warframe.market/v2/items` — tradable item catalog.
- `GET https://api.warframe.market/v2/orders/item/{slug}` — current buy/sell
  orders.
- `GET https://api.warframe.market/v2/user/{slug}` — public profile details,
  including the in-game name and platform.
- `GET https://api.warframe.market/v2/orders/user/{slug}` — that profile's public
  orders, matched back to catalog items by `itemId`.
- `GET https://api.warframe.market/v1/items/{slug}/statistics` — completed-sale
  history. The v2 API does not currently expose a statistics route, so the
  legacy v1 statistics endpoint is still used for this part.
- Warframe public export data (`ExportSyndicates.json`) — the syndicate-to-item
  mapping bundled in `wfmarket/syndicates.py`. The mapping is intersected with
  the Warframe.market catalog at runtime.

The client:

- sends an identifying `User-Agent`;
- stays below the public 3 requests/second limit (it uses 2.8/second);
- retries rate-limit and temporary server errors with backoff;
- caches the item catalog for six hours in
  `%LOCALAPPDATA%\PlatScout\cache`;
- requests only the selected syndicate's offerings, not every listing on the
  site;
- keeps the fetched order and statistics payloads in memory so rank and view
  filters can be changed without another request.

The app is read-only and never logs in, creates orders or changes anything on
Warframe.market.

## Project layout

```text
app.py                     Entry point and DPI setup
run.bat                    Windows setup/launcher
wfmarket/
  api.py                   Rate-limited API client, retries and catalog cache
  syndicates.py            Syndicate definitions and offering slug mapping
  analysis.py              Order/statistics filtering and profitability scoring
  users.py                 Profile slug parsing, listing filters and comparisons
ui/
  main_window.py           CustomTkinter window, layout, threading and queue
  frozen_tree.py           Paired Treeviews with frozen, reorderable columns
  preferences.py           Saved column order/visibility under LocalAppData
  chart.py                 Embedded matplotlib sales chart
  theme.py                 Shared colours
tests/
  test_analysis.py         Offline unit tests for analysis and catalog rules
  test_users.py            Offline tests for profile and listing comparison rules
  test_preferences.py      Offline tests for saved column-order/visibility
```

## Tests

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

## Known limitations

- Warframe.market's completed-sale statistics are grouped by hour/day and by
  rank; the app filters them to the selected rank but cannot recover individual
  trades that the API has already aggregated.
- "Volume" is the API's completed-trade count, not necessarily the number of
  physical copies traded.
- The minimum-sales filter deliberately uses 48-hour volume. Items with only
  older 30-day data are hidden while the threshold is above zero.
- Loading is limited by Warframe.market's public request rate. A 67-item
  syndicate such as Arbiters of Hexis needs at least about 48 seconds for its
  134 order/statistics requests. Market and listing loads share the same limiter,
  so starting both together does not increase the request rate.
- The score is an estimate. Actual selling speed depends on how you list,
  region, time of day and competition.
- Warframe.market has no public user-search endpoint. The app converts an
  in-game name to an approximate profile slug; names that collide with another
  profile (for example, one with a numeric suffix) or have legacy slug spelling
  need the full profile URL.
- The public user-orders endpoint ignores the platform header. Listing
  comparisons are disabled unless the profile's platform matches the selected
  platform.
- The frozen **Item** column cannot be hidden; all other columns can be toggled.
- The listings sidebar is always visible but shows only visible mod and arcane
  sell orders after you load a profile. It is loaded on demand and does not
  update automatically.
- The sales chart has a minimum height. On a small screen, use **Pop out** to
  inspect a chart without squeezing the rest of the window.
- The syndicate offering map is a bundled snapshot. Warframe updates can add or
  move items; update the slug sets in `wfmarket/syndicates.py` when that
  happens.
- The app is not affiliated with Digital Extremes or Warframe.market.
