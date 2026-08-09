// Shared price cache in front of brsapi.ir + navasan.tech for Gheymat
// Morabba. Every install used to call brsapi.ir directly with the same
// embedded key, so a handful of users on a short refresh interval could
// spend the whole account's daily quota by themselves. This worker is
// the only thing that still calls brsapi/navasan directly; every app
// install reads from here instead, so origin call volume stops scaling
// with how many people are running the app.
//
// One KV key ("snapshot") holds the last-known raw response for each of
// the three brsapi endpoints plus navasan, each with its own fetched_at.
// A cron tick that fails to reach one endpoint keeps the previous value
// for that one instead of overwriting good data with null.
//
// Two free-tier constraints shaped the numbers below:
//   - Workers KV free tier caps out at 1,000 writes/day. A 1-minute
//     cron (Ata's original cadence) would blow past that even with a
//     single combined key, so this runs every 2 minutes instead
//     (~720 writes/day, comfortable margin).
//   - The read side is fronted by the Cache API (not KV reads) so
//     traffic from however many app installs are polling /prices
//     doesn't scale KV read usage at all -- see handlePrices below.

const PRIMARY_URL = (key) => `https://api.brsapi.ir/Market/Gold_Currency.php?key=${key}`;
const COMMODITY_URL = (key) => `https://api.brsapi.ir/Market/Commodity.php?key=${key}`;
const CRYPTO_URL = (key) => `https://api.brsapi.ir/Market/Cryptocurrency.php?key=${key}`;
const NAVASAN_URL = "http://api.navasan.tech/latest/";

// Matches ForwardPriceService.NAVASAN_MIN_INTERVAL_SECONDS on the Python
// side -- keep these two in sync if either one changes.
const NAVASAN_MIN_INTERVAL_MS = 6 * 60 * 60 * 1000;

const PRICES_EDGE_CACHE_SECONDS = 60;

async function fetchJson(url) {
  const res = await fetch(url, { cf: { cacheTtl: 0 } });
  if (!res.ok) {
    throw new Error(`${url} -> HTTP ${res.status}`);
  }
  return res.json();
}

async function refreshSnapshot(env) {
  const key = env.BRSAPI_KEY;
  if (!key) {
    console.log("BRSAPI_KEY secret not set -- skipping this tick");
    return;
  }

  const [primaryRes, commodityRes, cryptoRes] = await Promise.allSettled([
    fetchJson(PRIMARY_URL(key)),
    fetchJson(COMMODITY_URL(key)),
    fetchJson(CRYPTO_URL(key)),
  ]);

  const now = Date.now();
  const prevRaw = await env.PRICES.get("snapshot");
  const prev = prevRaw ? JSON.parse(prevRaw) : { meta: {} };
  const prevMeta = prev.meta || {};

  const snapshot = {
    primary: primaryRes.status === "fulfilled" ? primaryRes.value : prev.primary ?? null,
    commodity: commodityRes.status === "fulfilled" ? commodityRes.value : prev.commodity ?? null,
    crypto: cryptoRes.status === "fulfilled" ? cryptoRes.value : prev.crypto ?? null,
    navasan: prev.navasan ?? null,
    meta: {
      primary_fetched_at: primaryRes.status === "fulfilled" ? now : prevMeta.primary_fetched_at ?? null,
      commodity_fetched_at: commodityRes.status === "fulfilled" ? now : prevMeta.commodity_fetched_at ?? null,
      crypto_fetched_at: cryptoRes.status === "fulfilled" ? now : prevMeta.crypto_fetched_at ?? null,
      navasan_fetched_at: prevMeta.navasan_fetched_at ?? null,
    },
  };

  if (primaryRes.status === "rejected") console.log("primary fetch failed:", primaryRes.reason?.message);
  if (commodityRes.status === "rejected") console.log("commodity fetch failed:", commodityRes.reason?.message);
  if (cryptoRes.status === "rejected") console.log("crypto fetch failed:", cryptoRes.reason?.message);

  const navPrevTs = prevMeta.navasan_fetched_at ?? 0;
  if (env.NAVASAN_API_KEY && now - navPrevTs >= NAVASAN_MIN_INTERVAL_MS) {
    try {
      const url = `${NAVASAN_URL}?api_key=${env.NAVASAN_API_KEY}&item=usd_farda_buy,usd_farda_sell`;
      snapshot.navasan = await fetchJson(url);
      snapshot.meta.navasan_fetched_at = now;
    } catch (err) {
      console.log("navasan fetch failed:", err.message);
      // leave the previous navasan value + timestamp in place; a failed
      // attempt shouldn't reset the 6h clock and force back-to-back retries
    }
  }

  await env.PRICES.put("snapshot", JSON.stringify(snapshot));
}

async function handlePrices(request, env, ctx) {
  const cache = caches.default;
  const cacheKey = new Request(request.url, request);

  const cached = await cache.match(cacheKey);
  if (cached) return cached;

  const raw = await env.PRICES.get("snapshot");
  const snapshot = raw
    ? JSON.parse(raw)
    : { primary: null, commodity: null, crypto: null, navasan: null, meta: {} };

  const response = new Response(JSON.stringify(snapshot), {
    headers: {
      "content-type": "application/json; charset=utf-8",
      "cache-control": `public, max-age=${PRICES_EDGE_CACHE_SECONDS}`,
      "access-control-allow-origin": "*",
    },
  });

  ctx.waitUntil(cache.put(cacheKey, response.clone()));
  return response;
}

export default {
  async scheduled(event, env, ctx) {
    ctx.waitUntil(refreshSnapshot(env));
  },

  async fetch(request, env, ctx) {
    const url = new URL(request.url);

    if (url.pathname === "/prices") {
      return handlePrices(request, env, ctx);
    }

    if (url.pathname === "/health") {
      return new Response("ok");
    }

    return new Response("not found", { status: 404 });
  },
};
