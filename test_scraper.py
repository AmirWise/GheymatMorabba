"""
Standalone diagnostic script for ForwardPriceService.

This does NOT need the full app, CustomTkinter, or Tkinter -- only
`requests` and `beautifulsoup4`. Run this from inside your extracted
project folder (the one with core/, data/, ui/ in it) so the imports
below can find data/api.py and core/config.py.
"""

import sys
import traceback

print("=" * 70)
print("Gheymat Morabba -- Forward Price Scraper Diagnostic")
print("=" * 70)
print()

try:
    from data.api import forward_price_service, CRYPTO_SYMBOLS, BrsApiBudget
    from core.config import FORWARD_PRICE_ASSETS, config
except Exception as e:
    print("STOP: could not import the project code.")
    print("Make sure this file sits in the SAME folder as core/, data/, ui/")
    print(f"Python error: {e}")
    sys.exit(1)


def show(label, func):
    print(f"--- {label} ---")
    try:
        result = func()
        print(f"RESULT: {result}")
        if result is None:
            print("(None means this step failed -- see any warning above, "
                  "or re-run with more detail using --verbose)")
    except Exception:
        print("CRASHED. Full error below:")
        traceback.print_exc()
    print()


if "--verbose" in sys.argv:
    import logging
    logging.basicConfig(level=logging.DEBUG)

show("1. Bonbast proxy (amirhn.com) -- fiat spot rates", forward_price_service.fetch_bonbast_spot_rates)
show("2. TGJU.org -- gold & coin prices", forward_price_service.fetch_tgju_gold_and_coins)
show("3. Tetherland -- USDT/IRT rate", forward_price_service.fetch_tetherland_usdt_irt)
show("4. Nobitex -- USDT/IRT order book (fallback)", forward_price_service.fetch_nobitex_usdt_irt)
show("5. Global cross-rate for EUR", lambda: forward_price_service.get_global_cross_rate("EUR"))
show("6. Global ounce price (XAU/USD)", forward_price_service.get_global_xau_usd)

print("=" * 70)
print("Per-asset price check (FORWARD_PRICE_ASSETS + a couple of crypto symbols)")
print("=" * 70)
for symbol, name in FORWARD_PRICE_ASSETS.items():
    show(f"{symbol} ({name})", lambda s=symbol: forward_price_service.compute_forward_price(s))

for symbol in ("USDT", "BTC"):
    label = "real-time rate, not forward" if symbol != "USDT" else "real-time rate"
    show(f"{symbol} ({label})", lambda s=symbol: forward_price_service.get_usdt_irt_rate() if s == "USDT" else "n/a -- uses the app's own live spot price, not this service")

print("=" * 70)
print("Which TGJU slug actually worked for each gold/coin asset")
print("=" * 70)
print("(Cross-check these numbers against a real, current price you trust --")
print(" this is exactly how the IR_COIN_1G/EMAMI/BAHAR mapping bug was found")
print(" last time. If a slug looks wrong for what it returned, tell me and")
print(" I'll adjust TGJU_SLUG_CANDIDATES in data/api.py.)")
print()
for asset, slug in forward_price_service.resolved_tgju_slugs.items():
    print(f"  {asset}: resolved via slug '{slug}'")
if not forward_price_service.resolved_tgju_slugs:
    print("  (none resolved -- see the TGJU section above)")

print()
print("=" * 70)
print("BRSAPI daily budget (this install, resets at local midnight)")
print("=" * 70)
_budget = BrsApiBudget()
_total_cap = _budget.daily_total
_half_cap = _total_cap // 2
_status = _budget.status()
for category, label, cap in (
    ("gold_currency", "Gold_Currency", _half_cap),
    ("commodity", "Commodity", _half_cap),
    ("crypto", "Cryptocurrency", _total_cap),
):
    print(f"  {label}: {_status[category]} / {cap} used today")
print(f"  (combined total across all three: {sum(_status.values())} / {_total_cap})")
print("  Note: this only counts calls made by whichever copy of the app runs")
print("  this diagnostic -- it isn't visibility into brsapi's actual account-wide usage.")

print()
print("=" * 70)
print("Shared worker (cf-worker/) status")
print("=" * 70)
_worker_url = str(getattr(config, "WORKER_BASE_URL", "") or "").strip()
if not _worker_url:
    print("  Not configured (config.WORKER_BASE_URL / GHEYMAT_WORKER_URL is empty).")
    print("  The app is calling brsapi.ir and navasan.tech directly, just with")
    print("  the budget above protecting it. See cf-worker/README.md to deploy one.")
else:
    print(f"  Configured: {_worker_url}")

    def _check_worker():
        import requests
        resp = requests.get(f"{_worker_url.rstrip('/')}/prices", timeout=10)
        resp.raise_for_status()
        envelope = resp.json()
        return {k: (v is not None) for k, v in envelope.items() if k != "meta"}

    show("GET /prices -- which categories came back non-null", _check_worker)

print("Done. Copy everything above (from the very top) and send it back.")
