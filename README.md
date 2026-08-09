# 💎 Gheymat Morabba

**Real-time Currency • Crypto • Gold • Portfolio**

![Version](https://img.shields.io/badge/version-5.0.0-blue)
![Python](https://img.shields.io/badge/python-3.8%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Platform](https://img.shields.io/badge/platform-Windows-lightgrey)
![UI](https://img.shields.io/badge/UI-CustomTkinter-8A2BE2)

| Language | زبان |
|----------|------|
| [English](README.md) | [فارسی](README.fa.md) |

**Version:** 5.0.0
**Author:** AmirWise
**Repository:** [github.com/AmirWise/GheymatMorabba](https://github.com/AmirWise/GheymatMorabba)
**Previously known as:** Liquid Gheymat

---

Gheymat Morabba is a desktop dashboard for tracking Iranian Rial currency rates, gold and coin prices, select commodities, and 80+ cryptocurrencies — live, and, where it matters most, **a day ahead**. It's a from-the-ground-up rewrite of Liquid Gheymat: same spirit (fast, glass-inspired, bilingual), completely re-architected internals, and a genuinely new headline feature — real forward ("fardaee") price forecasting for fiat and gold.

## 📑 Table of Contents

- [What's New in v5.0.0](#whats-new-in-v500)
- [Features](#features)
- [Screenshots](#screenshots)
- [Architecture](#architecture)
- [Requirements](#requirements)
- [Installation & Quick Start](#installation--quick-start)
- [Configuration](#configuration)
- [Data Sources](#data-sources)
- [Self-Hosting a Shared Cache (Optional)](#self-hosting-a-shared-cache-optional)
- [Usage Guide](#usage-guide)
- [Diagnostics](#diagnostics)
- [FAQ / Troubleshooting](#faq--troubleshooting)
- [Security Notes](#security-notes)
- [Contributing](#contributing)
- [Disclaimer](#disclaimer)
- [License](#license)
- [Acknowledgments](#acknowledgments)

---

## ✨ What's New in v5.0.0

### At a glance

| | v4.0.0 — *Liquid Gheymat* | v5.0.0 — *Gheymat Morabba* |
|---|---|---|
| Codebase | One file, ~5,300 lines | Layered `core/` · `data/` · `ui/` packages, mixin-composed window |
| Market coverage | One blended feed | **Normal** and **Crypto** modes, each with its own sources and portfolio |
| Pricing | Live spot prices only | Live prices **+ forward ("fardaee") forecasts** for fiat & gold |
| Themes | 6 (incl. Vibrancy, Midnight) | 4 refined themes (Liquid Glass, Crystal, Paper, Paper Noir) |
| Navigation | Every section always on screen | Compact primary dashboard + floating Quick Access menu |
| Reliability | Retries + circuit breaker | + local daily call-budget guard, optional shared cache, session tracker |
| Window management | Basic | Single-instance lock, tray/background mode, DPI-aware sizing |

### Why the rewrite?

v4 worked, but it lived in one ~5,300-line file where UI, networking, persistence, and theming were all tangled together. Every change meant scrolling through thousands of lines to find the one method that mattered. v5 splits those concerns cleanly (see [Architecture](#architecture)) so each piece — a data source, a dashboard section, a theme — can be read, tested, and changed on its own.

### Highlights

- **🪙 Two focused market modes** — Normal (fiat, gold, coins, commodities) and Crypto (80+ coins), each with its own data sources, featured symbols, price-basis toggle, and — importantly — its own portfolio. Switching modes never mixes the two.
- **📈 Forward price forecasting** — click any eligible card to see tomorrow's estimated price instead of just today's, sourced from a cascading chain of providers so one outage doesn't take the feature down.
- **⚡ Floating Quick Access menu** — the dashboard now shows only what matters most (Hero, Featured Markets, Your Portfolio, Market Insights, Status); everything else — settings, converter, widgets, alerts, layout — lives one tap behind the floating `⋮` button.
- **🧩 Smarter desktop widgets** — theme-aware, RTL-aware, and properly tucked behind other apps instead of floating over them.
- **🛡️ A backend that protects itself** — a local daily call-budget guard and an optional shared cache mean one busy user can no longer burn through a quota that every other install depends on.
- **🪟 Single-instance app** — launching it twice just brings the existing window to the front.
- **📐 Rearrangeable dashboard** — drag sections up/down or hide the ones you don't use (a few are load-bearing and always stay visible).
- **🖥️ DPI-aware, screen-proportional window sizing** — no more a fixed 1200×900 window looking tiny on a 4K monitor or oversized on a small laptop.

---

## 🖥️ Features

### 🪙 Two Focused Market Modes
- **Normal mode** — fiat currencies (USD, EUR, GBP, AED, TRY, and 20+ more), domestic gold and coin prices, and select metals/energy commodities.
- **Crypto mode** — a dedicated live feed of 80+ cryptocurrencies (BTC, ETH, USDT, BNB, SOL, XRP, ADA, DOGE, and more), each priced in both Toman and USD, with market cap and category info.
- Each mode keeps its **own portfolio** in the local database — a coin you track in Crypto mode never shows up in Normal mode, and vice versa.
- Each mode has its own price-basis toggle next to the Quick Access button: Normal mode flips between Toman and USD; Crypto mode flips between Toman and USDT.

### 📈 Forward ("Fardaee") Price Popup
Tap any card for a fiat currency, gold type, or coin, and Gheymat Morabba shows tomorrow's forecast price — not just today's spot rate. 9 gold/coin instruments and 27 fiat currencies are covered. Crypto cards instead show a live, real-time rate, since crypto markets don't really have a "tomorrow" price the way domestic gold and currency markets do.

### 💼 Portfolio Management
- A searchable, scrollable currency picker — replacing the native dropdown, which had no mouse-wheel or search support.
- Sort by name, symbol, price, or % change; filter with a quick text search.
- Everything you explicitly add stays visible in your portfolio, even if it also happens to be currently "Featured."

### ⚡ Market Insights & Session Tracker
- Top 3 gainers and top 3 losers at a glance.
- A lightweight **Session Tracker** shows how far each watched price has moved since you opened the app — no charting overhead, just the numbers that matter, reset each time you relaunch.

### 🔔 Price Alerts
- Set a percentage move threshold; get a toast the instant a tracked price crosses it (with a per-symbol cooldown so you're not spammed).
- The last 30 alerts stay in a rolling log, viewable from the Quick Access menu.

### 🧩 Desktop Widgets *(Windows only)*
- Pin a price card, a top-movers panel, or a mini portfolio summary directly onto your desktop.
- Draggable, and themeable independently of the main window — "Auto" follows the app's active theme, or pick one explicitly.
- Automatically hides behind other windows and reappears over the desktop, so it never overlays whatever you're actually working in.

### 🎨 Theming & Bilingual UI
- Four refined themes — **Liquid Glass**, **Crystal**, **Paper**, and **Paper Noir** — each with a real acrylic/blur window effect on Windows (via `pywinstyles`) and a graceful simulated fallback everywhere else.
- Full English and Persian localization with true RTL layout mirroring — not just translated strings, the whole interface flips.

### 🛡️ Built for Reliability
- Automatic retries with backoff and a circuit breaker that stops hammering a dead endpoint after repeated failures.
- A local daily call-budget guard, since every installation currently shares one API key (see [Data Sources](#data-sources)).
- Instant startup from a local SQLite cache; live data arrives moments later in the background.
- A single-instance guard: a second launch just focuses the window that's already open.

---

## 🧱 Architecture

v5 is organized into three layers, each with one job:

- **`core/`** — configuration, cross-platform utilities, theming, and translations. No UI code, no network calls.
- **`data/`** — everything that talks to the outside world: `api.py` (market data + forward-price scraping) and `db.py` (SQLite persistence).
- **`ui/`** — the dashboard itself. `MainWindow` (in `app.py`) is composed from focused mixins — `WindowMixin`, `StartupMixin`, `LocalizationMixin`, `LayoutMixin`, `FabMixin`, `PortfolioActionsMixin`, `ThemeMixin`, and more — each owning one concern but sharing state through `self`, so the class can be read and changed one piece at a time.

### Project structure

```
Gheymat-Morabba/
├── main.py                    # Entry point: single-instance guard, diagnostics, mainloop
├── test_scraper.py            # Standalone diagnostic script for every data source
├── requirements.txt
├── README.md
├── README.fa.md
├── LICENSE
│
├── core/
│   ├── config.py               # AppConfiguration, ConnectionStatus, FORWARD_PRICE_ASSETS
│   ├── utils.py                 # Logging, platform helpers, single-instance IPC
│   ├── theme.py                 # ThemeManager + color palette
│   ├── theme.json                # CustomTkinter native theme file
│   └── i18n.py                    # English/Persian translation tables
│
├── data/
│   ├── api.py                      # APIManager, BrsApiBudget, ForwardPriceService
│   └── db.py                        # DatabaseManager (SQLite)
│
├── ui/
│   ├── app.py                        # MainWindow (composed from the mixins below)
│   ├── widgets.py                     # CurrencyCardWidget, SparklineCanvas
│   ├── ui_support.py                   # Visual effects, performance counters, toasts
│   ├── desktop_widgets.py               # Desktop widgets + system tray
│   ├── mixin_foundation.py               # Window setup, startup, localization, preferences
│   ├── mixin_layout.py                    # Dashboard layout, FAB, section customization
│   ├── mixin_sections.py                   # History/Converter/Widgets sections
│   └── mixin_actions.py                     # Portfolio, settings, and theme actions
│
├── assets/
│   ├── fonts/Vazirmatn-Regular.ttf
│   └── icons/icon.ico
│
└── cf-worker/                  # Optional: a shared-cache Cloudflare Worker (see below)
    ├── wrangler.toml
    ├── src/worker.js
    └── test/logic.test.mjs
```

---

## ⚙️ Requirements

- **Windows 10** (build 1903+) or **Windows 11** — recommended for full feature support (desktop widgets, tray icon, native acrylic/blur, dark title bar). The core dashboard also runs on macOS/Linux, just without those Windows-specific integrations.
- **Python 3.8+**
- An internet connection for live data — the app still opens and shows the last cached prices when offline.
- *(Optional)* A free Cloudflare account, only if you plan to self-host the shared-cache worker.

---

## 🚀 Installation & Quick Start

```bash
git clone https://github.com/AmirWise/GheymatMorabba.git
cd Gheymat-Morabba
pip install -r requirements.txt
```

Set up your API keys — see [Configuration](#configuration) below — then run:

```bash
python main.py
```

On first launch, the app paints instantly from local cache and fetches live data in the background.

---

## 🔑 Configuration

Gheymat Morabba is designed to run on **your own API keys**, supplied as environment variables — nothing is meant to ship hardcoded in the repository.

| Variable | What it's for | Required? | Notes |
|---|---|---|---|
| `BRSAPI_KEY` | Your BRSAPI key, used to build the Gold_Currency, Commodity, and Cryptocurrency endpoint URLs | **Yes** | Core market data won't load without it — get one at [brsapi.ir](https://brsapi.ir) |
| `NAVASAN_API_KEY` | Enables a genuine forward ("fardaee") USD rate | No | Without it, the forward-price popup falls back to a Tether-derived USD estimate |
| `BRSAPI_DAILY_BUDGET` | Local soft cap on daily BRSAPI calls, shared across all three endpoints | No | Defaults to `10000` — lower it to match your actual plan's quota |
| `GHEYMAT_WORKER_URL` | Base URL of a shared-cache backend you control | No | If unset, the app calls BRSAPI / Tetherland / Navasan directly (see [Self-Hosting](#self-hosting-a-shared-cache-optional)) |

### Setting them

**PowerShell (current session):**
```powershell
$env:BRSAPI_KEY = "your-key-here"
$env:NAVASAN_API_KEY = "your-key-here"   # optional
```

**PowerShell (permanent):**
```powershell
setx BRSAPI_KEY "your-key-here"
```

**macOS / Linux / Git Bash:**
```bash
export BRSAPI_KEY="your-key-here"
export NAVASAN_API_KEY="your-key-here"   # optional
```

**Or, with a `.env` file** (make sure it's listed in `.gitignore`):
```
# .env
BRSAPI_KEY=your-key-here
NAVASAN_API_KEY=your-key-here
```
Load it at the very top of `main.py` with [`python-dotenv`](https://pypi.org/project/python-dotenv/):
```python
from dotenv import load_dotenv
load_dotenv()
```

---

## 🌐 Data Sources

Here's exactly where every number in the app comes from, and how to get access to each source yourself.

| Purpose | Provider | Access | Get it |
|---|---|---|---|
| Gold, currency & coin prices (Normal mode) | BRSAPI — *Gold_Currency* endpoint | API key | [brsapi.ir](https://brsapi.ir) |
| Metals & energy commodities | BRSAPI — *Commodity* endpoint | API key | [brsapi.ir](https://brsapi.ir) |
| Cryptocurrency prices (Crypto mode) | BRSAPI — *Cryptocurrency* endpoint | API key | [brsapi.ir](https://brsapi.ir) |
| USDT/Toman rate, Toman-priced pairs | Tetherland | Public endpoint, no key | [tetherland.com](https://tetherland.com) |
| Genuine forward ("fardaee") USD rate | Navasan | Free API key | Telegram: [@navasan_contact_bot](https://t.me/navasan_contact_bot) |
| Fallback fiat/gold rates | alanchand.com | Scraped public page | — |
| Fallback USD reference + coin rates | bonbast.amirhn.com | Public JSON mirror | — |
| Fallback gold/coin data | tgju.org | Scraped public profile page | — |
| USDT/IRT order-book fallback | Nobitex | Public endpoint, no key | [nobitex.ir](https://nobitex.ir) |
| Fiat cross-rate fallback | ExchangeRate-API | Public endpoint, no key | [exchangerate-api.com](https://www.exchangerate-api.com) |
| Historical sparkline data (crypto) | CoinGecko | Public, rate-limited | [coingecko.com](https://www.coingecko.com) |

### About the API sources

- **BRSAPI** — an Iranian market-data API covering gold, currency, and crypto. Sign up, subscribe to the three endpoints above, and use the key you're issued. Free and paid tiers both exist; the app's built-in `BrsApiBudget` is a client-side safety net regardless of which plan you're on.
- **Navasan** — message [@navasan_contact_bot](https://t.me/navasan_contact_bot) on Telegram for a free key. This unlocks a genuine forward USD quote in the Forward Price popup, labeled honestly as such; without it, the same popup shows a live Tether-derived estimate instead.
- **Tetherland / Nobitex / ExchangeRate-API / CoinGecko** — all called against public, keyless endpoints in the current implementation. CoinGecko in particular is rate-limited on its free tier; get a Demo API key from their site if you outgrow it.

### About the scraped sources

**alanchand.com**, **tgju.org**, and the **bonbast.amirhn.com** mirror don't have formal APIs — Gheymat Morabba fetches their public pages with `requests` and parses the HTML with `BeautifulSoup`, the same way a browser would render them, just without a UI. Because there's no API contract, page-structure changes can break a scraper at any moment; that's exactly why each of these sits behind a fallback chain in `ForwardPriceService` rather than being a single point of failure.

If you build on this, scrape considerately: cache aggressively (the app already does, via `CACHE_TTL_SECONDS` and SQLite persistence), don't shorten the refresh interval specifically to hit these pages harder, and check each site's current terms of use before deploying at any real scale.

---

## ☁️ Self-Hosting a Shared Cache (Optional)

If you're distributing this app to more than a handful of people under one BRSAPI key, deploy the included Cloudflare Worker as a shared cache in front of your own key, so read traffic from every install never scales your own API usage:

1. `cd cf-worker`
2. `wrangler login`
3. Create a KV namespace and update the `id` in `wrangler.toml`
4. Set your secrets: `wrangler secret put BRSAPI_KEY` *(and, optionally, `wrangler secret put NAVASAN_API_KEY`)*
5. `wrangler deploy`
6. Point every app install at it by setting `GHEYMAT_WORKER_URL` to your deployed Worker's URL

The Worker refreshes its cache on a 2-minute cron and serves `/prices` from Cloudflare's edge Cache API — so read traffic from any number of app installs never touches Workers KV, only the cron tick does. `cf-worker/test/logic.test.mjs` has a small, self-contained test suite for the caching and fallback logic if you want to verify a change before deploying.

---

## 📚 Usage Guide

### The Dashboard
On launch you'll see, in order: a **Hero** header, **Featured Markets** (a row of the most relevant symbols for your current mode), **Your Portfolio**, and **Market Insights** (top gainers/losers). Everything else is one tap away.

### Managing Your Portfolio
Tap **➕ Add to Portfolio**, search, and tap a result to add it instantly. Use the sort dropdown to order by name, symbol, price, or change, and the 🔍 button to reveal a quick text filter. Remove anything with the ✕ on its card.

### Forward Price Popup
Tap any eligible card to open its popup. Fiat/gold/coin cards show a **spot price** and a **forward ("fardaee") price**; crypto cards show a **live rate** instead, labeled accordingly.

### Quick Access Menu
Tap the floating `⋮` button in the bottom corner to reach:

| Item | What it does |
|---|---|
| 🪙 Mode | Switch between Normal and Crypto |
| 🔄 Refresh Now | Force an immediate data refresh |
| 🌐 Language | Toggle English ⇄ Persian |
| 🎨 Theme | Pick Liquid Glass, Crystal, Paper, or Paper Noir |
| 📌 Session Tracker | See how much each watched price has moved this session |
| 🔔 Alerts | Enable/adjust alerts and view the recent-alerts log |
| 🧪 Test API | Run a quick connectivity/parse check against the live feed |
| 📄 Export CSV | Export your featured + portfolio data |
| 🧹 Clear Cache | Wipe the local price cache |
| 📈 Performance | View runtime stats (UI updates, API calls, cache loads, errors) |
| 🧮 Converter | Convert between any two tracked currencies |
| 🧩 Desktop Widgets | Add/remove pinned desktop widgets |
| 🎛️ Data Controls | Manual refresh, API test, export, and auto-refresh toggle |
| ⚙️ Settings | Language, window options, alert threshold, refresh interval |
| 📐 Manage Sections | Reorder or hide dashboard sections |

### Desktop Widgets *(Windows)*
From the Quick Access menu, open **Desktop Widgets**, pick a type (Price card / Top movers / Portfolio mini) and, for a price card, a symbol — then **➕ Add Widget**. Drag it anywhere on your desktop. Enable **Run in background** in Settings if you want widgets to survive minimizing the main window.

### Keyboard Shortcuts

| Shortcut | Action |
|---|---|
| `Ctrl + R` / `F5` | Manual refresh |
| `Ctrl + F` | Focus the portfolio search |
| `Ctrl + Q` | Quit (or hide to tray, if background mode is on) |
| `Esc` | Dismiss active toast notifications |

### Running in the Background
Enable **Run in background when closing** in Settings, and the ✕ button minimizes to the system tray instead of exiting — auto-refresh and desktop widgets keep working. Double-click the tray icon, or right-click → Open, to bring the window back.

---

## 🧪 Diagnostics

`test_scraper.py` is a standalone script (no Tkinter/CustomTkinter needed) that exercises every data source independently of the GUI — Bonbast, TGJU, Tetherland, Nobitex, the global cross-rate, forward-price computation for every whitelisted asset, and your shared worker if one is configured:

```bash
python test_scraper.py
python test_scraper.py --verbose   # with debug-level logging
```

Run this first whenever a specific price stops updating — it tells you exactly which upstream source is failing before you go looking anywhere else.

---

## ❓ FAQ / Troubleshooting

**I switched to Crypto mode and my portfolio disappeared!**
It didn't — Normal and Crypto mode each keep a completely separate portfolio on purpose, so a coin you track in Crypto mode never clutters your fiat/gold view. Switch back and it'll be exactly as you left it.

**Prices stopped updating.**
Check the API status pill at the top of the dashboard. "Rate limited" or "Offline" usually means the circuit breaker or the daily call-budget guard has kicked in after repeated failures — this is intentional and recovers on its own. Run `test_scraper.py` to see exactly which source is failing.

**The USD forward price looks like an estimate, not an exact number.**
Without a `NAVASAN_API_KEY`, the forward-price popup for USD falls back to a live Tether-derived rate and labels itself accordingly. Add a free Navasan key (see [Configuration](#configuration)) for a genuine forward quote.

**Desktop widgets vanish when I minimize the app.**
Enable **Run in background** in Settings first — otherwise minimizing/closing fully exits the process and takes the widgets with it.

**I opened the app again and nothing new happened.**
That's by design — Gheymat Morabba is single-instance. A second launch just focuses the window that's already open.

**A specific scraped price (gold/coin/fiat) looks wrong or stale.**
Each of those falls back through several public sources; if the top one changed its page layout, the fallback chain should mostly cover it. Please open an issue so the affected slug/selector can be updated.

**Where do I get an API key?**
See [Data Sources](#data-sources) above — BRSAPI is required, everything else is optional and only improves accuracy or unlocks a feature.

---

## 🔒 Security Notes

- Never commit real API keys, tokens, or secrets to a public repository. Use environment variables, or a local, `.gitignore`d `.env` file — not literal values inside `core/config.py`.
- If a key or secret is ever committed by mistake, treat it as compromised: rotate it immediately, even after removing it from the latest commit, since it remains visible in the repository's history until that history itself is rewritten.
- If you deploy your own shared-cache backend (see [Self-Hosting](#self-hosting-a-shared-cache-optional)), keep its credentials as platform secrets (e.g. `wrangler secret put`), never in source.

---

## 🤝 Contributing

Contributions are welcome!

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/your-feature`
3. If you're adding new dashboard behavior, consider whether it belongs in an existing mixin or deserves its own (see `ui/mixin_*.py`) — one concern per mixin keeps the codebase easy to navigate
4. Commit your changes with a clear message
5. Push to your branch and open a Pull Request

Please keep the existing code style, and add a comment or docstring when a piece of logic isn't obvious from its name alone.

---

## ⚠️ Disclaimer

Gheymat Morabba aggregates unofficial, publicly available reference rates for currencies, gold, coins, commodities, and cryptocurrencies. These figures are provided for personal, informational tracking only — they are **not** official exchange rates, are not guaranteed to be accurate or timely, and should not be used as the sole basis for any financial or trading decision. Always verify with an authoritative source before acting on any price shown here.

---

## 📄 License

Distributed under the **MIT License**. See [`LICENSE`](LICENSE) for the full text.

---

## 🙏 Acknowledgments

Thanks to the teams and communities behind **BRSAPI**, **Tetherland**, **Navasan**, **Nobitex**, **CoinGecko**, **ExchangeRate-API**, **alanchand.com**, **tgju.org**, and the maintainers of the open Bonbast mirror at **bonbast.amirhn.com** — this project would just be a nice-looking window without the data they make publicly available.

Built with [CustomTkinter](https://github.com/TomSchimansky/CustomTkinter), `requests`, `beautifulsoup4`, `pyglet`, and [`pywinstyles`](https://github.com/Akascape/py-window-styles). Persian text is set in [Vazirmatn](https://github.com/rastikerdar/vazirmatn) by Saber Rastikerdar.
