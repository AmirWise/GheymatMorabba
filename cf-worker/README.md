# Shared price cache (Cloudflare Worker)

This is the "everyone reads from one cache instead of everyone hitting
brsapi.ir with the same key" piece. It's the same idea as the polling
system Ata described (one process fetches on a schedule, everything
else reads the fetched copy), just built on Cloudflare Workers + KV
instead of a VPS + database, since neither is needed for a dataset this
small.

It's optional. Nobody has to deploy this for the app to work --
`core/config.py`'s `WORKER_BASE_URL` defaults to empty, and with it
empty the app calls brsapi.ir/navasan.tech directly, same as before,
just with the new local daily-budget split protecting it. Deploy this
once you actually want every install reading from one shared cache
instead of hitting brsapi directly.

## What it does

Every 2 minutes, a Cron Trigger fetches all three brsapi Market
endpoints (Gold_Currency, Commodity, Cryptocurrency) and stores the raw
responses in a single KV key. Every 6 hours (tracked independently of
the price tick) it also fetches Navasan's forward-USD rate the same
way. The app then reads `GET /prices` instead of calling brsapi/navasan
directly, and gets back:

```json
{
  "primary": { /* raw Gold_Currency.php response, or null */ },
  "commodity": { /* raw Commodity.php response, or null */ },
  "crypto": { /* raw Cryptocurrency.php response, or null */ },
  "navasan": { /* raw navasan.tech response, or null */ },
  "meta": {
    "primary_fetched_at": 1234567890000,
    "commodity_fetched_at": 1234567890000,
    "crypto_fetched_at": 1234567890000,
    "navasan_fetched_at": 1234567890000
  }
}
```

Everything is passed through raw, byte-for-byte what brsapi/navasan
returned -- this worker doesn't reimplement any of the parsing logic
already in `data/api.py`. That logic (`process_currency_data` and
friends) already handles this exact shape, since it's the same shape
it always got directly. Changing the source of the bytes doesn't
require changing anything else.

If a single endpoint fails on a given tick, that key keeps its
previous value instead of going null -- a bad brsapi response for
Commodity shouldn't wipe out an otherwise-fine snapshot.

## Why every 2 minutes and not every 1 minute

Workers KV's free tier caps out at 1,000 writes/day per account. This
worker writes one combined key per tick, so:

- Every 1 minute -> 1,440 writes/day -- over the cap.
- Every 2 minutes -> 720 writes/day -- comfortable margin.

If you want Ata's original 1-minute cadence, that needs the $5/month
Workers paid plan (1M KV writes/month included, i.e. effectively
unlimited for this use case) -- still nothing close to a VPS. Change
the cron line in `wrangler.toml` if you go that route.

Reads don't have the same problem: `GET /prices` is fronted by the
Workers Cache API with a 60-second edge cache, so read volume from
however many app installs are polling doesn't scale KV reads at all --
each edge location only actually touches KV once per 60-second window
regardless of how many requests hit it in that window.

## Deploying

You'll need a (free) Cloudflare account and Node.js for the Wrangler
CLI. From this `cf-worker/` folder:

```bash
npx wrangler login
```

This opens a browser to authorize the CLI against your account.

```bash
npx wrangler kv namespace create PRICES
```

This prints an `id`. Paste it into `wrangler.toml`, replacing
`REPLACE_WITH_YOUR_KV_NAMESPACE_ID`.

```bash
npx wrangler secret put BRSAPI_KEY
```

Paste your actual brsapi.ir key when prompted (the same one currently
sitting in `core/config.py` -- this is where it stops needing to live
in source at all, at least for whatever build points at this worker).

```bash
npx wrangler secret put NAVASAN_API_KEY
```

Paste your Navasan key. If you skip this one, the worker just never
populates the `navasan` field and the app's own Tether-derived fallback
keeps covering for it -- same graceful-degradation behavior as before.

```bash
npx wrangler deploy
```

This prints the deployed URL, something like
`https://gheymat-morabba-prices.<your-subdomain>.workers.dev`.

Check it's alive:

```bash
curl https://gheymat-morabba-prices.<your-subdomain>.workers.dev/health
```

The cron won't have run yet on a fresh deploy, so `/prices` will come
back with everything `null` until the first tick (up to 2 minutes).
You can also trigger it manually to check sooner:

```bash
npx wrangler deployments list
npx wrangler tail        # watch live logs from a real cron tick
```

or, to run the scheduled handler once locally without waiting:

```bash
npx wrangler dev --test-scheduled
curl "http://localhost:8787/__scheduled?cron=*/2+*+*+*+*"
```

## Pointing the app at it

Set the `GHEYMAT_WORKER_URL` environment variable before launching the
app, or hardcode it as `WORKER_BASE_URL`'s default in
`core/config.py`:

```python
WORKER_BASE_URL: str = os.environ.get("GHEYMAT_WORKER_URL", "https://gheymat-morabba-prices.<your-subdomain>.workers.dev")
```

Once that's set, `APIManager` and `ForwardPriceService` try this
worker first on every fetch and only fall back to calling brsapi/
navasan directly if the worker call fails or isn't configured -- so a
build without this set up still runs exactly as before.

## What this doesn't cover

Tetherland (the USDT/IRT rate used for the crypto-mode price-basis
toggle) isn't part of this -- it's a different provider, not subject to
the same shared-key problem, so `fetch_tether_irr_rate_sync` still
calls it directly regardless of whether a worker is configured.

There's no auth on `/prices` -- anyone with the URL can read it, which
is the point (that's the whole app's audience), but it also means
there's no way to stop someone else from pointing their own copy of
the app at your worker. Cloudflare's free plan gives 100,000 requests/
day; if that ever becomes the binding constraint rather than brsapi's
own limit, that's a nicer problem to have than the current one.
