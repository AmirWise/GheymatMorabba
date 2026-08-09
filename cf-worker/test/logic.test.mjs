// Exercises refreshSnapshot()/handlePrices() against a fake KV + fetch,
// since there's no real Cloudflare account reachable from here. Not
// shipped -- just how I checked the logic before handing it over.

import assert from "node:assert/strict";

// ---- fake KV ----
function makeKv(initial = {}) {
  const store = new Map(Object.entries(initial));
  return {
    async get(key) {
      return store.has(key) ? store.get(key) : null;
    },
    async put(key, value) {
      store.set(key, value);
    },
    _dump() {
      return Object.fromEntries(store);
    },
  };
}

// ---- fake edge cache ----
function makeCacheStore() {
  const store = new Map();
  return {
    default: {
      async match(req) {
        return store.get(req.url) || null;
      },
      async put(req, res) {
        store.set(req.url, res);
      },
    },
    _size() {
      return store.size;
    },
  };
}

async function run() {
  const mod = await import("../src/worker.js");
  const { default: worker } = mod;

  async function runScheduled(env) {
    let pending;
    const ctx = { waitUntil: (p) => { pending = p; } };
    await worker.scheduled({}, env, ctx);
    await pending; // real Workers don't await this inside scheduled() itself, but the test needs to before asserting
  }

  // ---- Test 1: first-ever tick, all three succeed ----
  {
    let callLog = [];
    globalThis.fetch = async (url) => {
      callLog.push(url);
      if (url.includes("Gold_Currency")) return { ok: true, json: async () => ({ gold: 1 }) };
      if (url.includes("Commodity")) return { ok: true, json: async () => ({ oil: 2 }) };
      if (url.includes("Cryptocurrency")) return { ok: true, json: async () => ({ btc: 3 }) };
      throw new Error("unexpected url " + url);
    };

    const env = { PRICES: makeKv(), BRSAPI_KEY: "k", NAVASAN_API_KEY: "" };
    await runScheduled(env);
    const snap = JSON.parse(await env.PRICES.get("snapshot"));
    assert.deepEqual(snap.primary, { gold: 1 });
    assert.deepEqual(snap.commodity, { oil: 2 });
    assert.deepEqual(snap.crypto, { btc: 3 });
    assert.equal(snap.navasan, null, "no NAVASAN_API_KEY set -> navasan stays null");
    console.log("test 1 (fresh tick, all succeed) OK");
  }

  // ---- Test 2: partial failure keeps the previous good value ----
  {
    const prevSnapshot = {
      primary: { gold: 999 },
      commodity: { oil: 999 },
      crypto: { btc: 999 },
      navasan: null,
      meta: { primary_fetched_at: 111, commodity_fetched_at: 111, crypto_fetched_at: 111, navasan_fetched_at: null },
    };
    const env = { PRICES: makeKv({ snapshot: JSON.stringify(prevSnapshot) }), BRSAPI_KEY: "k", NAVASAN_API_KEY: "" };

    globalThis.fetch = async (url) => {
      if (url.includes("Gold_Currency")) return { ok: true, json: async () => ({ gold: 1 }) };
      if (url.includes("Commodity")) throw new Error("simulated commodity outage");
      if (url.includes("Cryptocurrency")) return { ok: true, json: async () => ({ btc: 3 }) };
      throw new Error("unexpected url " + url);
    };

    await runScheduled(env);
    const snap = JSON.parse(await env.PRICES.get("snapshot"));
    assert.deepEqual(snap.primary, { gold: 1 }, "primary should update");
    assert.deepEqual(snap.commodity, { oil: 999 }, "commodity should keep the previous value on failure");
    assert.deepEqual(snap.crypto, { btc: 3 }, "crypto should update");
    console.log("test 2 (partial failure preserves stale-but-good data) OK");
  }

  // ---- Test 3: navasan respects the 6h gate ----
  {
    const now = Date.now();
    const recentNavasan = {
      primary: null, commodity: null, crypto: null,
      navasan: { usd_farda_buy: { value: "100" } },
      meta: { navasan_fetched_at: now - 60 * 1000 }, // 1 minute ago
    };
    const env = { PRICES: makeKv({ snapshot: JSON.stringify(recentNavasan) }), BRSAPI_KEY: "k", NAVASAN_API_KEY: "navkey" };
    let navasanCalled = false;
    globalThis.fetch = async (url) => {
      if (url.includes("navasan.tech")) {
        navasanCalled = true;
        return { ok: true, json: async () => ({ usd_farda_buy: { value: "200" } }) };
      }
      return { ok: true, json: async () => ({}) };
    };
    await runScheduled(env);
    assert.equal(navasanCalled, false, "navasan must not be called again inside the 6h window");
    const snap = JSON.parse(await env.PRICES.get("snapshot"));
    assert.equal(snap.navasan.usd_farda_buy.value, "100", "stale-but-fresh-enough navasan value should be kept as-is");
    console.log("test 3 (navasan 6h gate holds) OK");
  }

  // ---- Test 4: navasan fetch fires once outside the 6h window ----
  {
    const now = Date.now();
    const staleNavasan = {
      primary: null, commodity: null, crypto: null,
      navasan: { usd_farda_buy: { value: "100" } },
      meta: { navasan_fetched_at: now - 7 * 60 * 60 * 1000 }, // 7 hours ago
    };
    const env = { PRICES: makeKv({ snapshot: JSON.stringify(staleNavasan) }), BRSAPI_KEY: "k", NAVASAN_API_KEY: "navkey" };
    let navasanCalled = false;
    globalThis.fetch = async (url) => {
      if (url.includes("navasan.tech")) {
        navasanCalled = true;
        return { ok: true, json: async () => ({ usd_farda_buy: { value: "200" } }) };
      }
      return { ok: true, json: async () => ({}) };
    };
    await runScheduled(env);
    assert.equal(navasanCalled, true, "navasan should be called again once past the 6h window");
    const snap = JSON.parse(await env.PRICES.get("snapshot"));
    assert.equal(snap.navasan.usd_farda_buy.value, "200", "navasan value should refresh once the window passes");
    console.log("test 4 (navasan refetches after 6h) OK");
  }

  // ---- Test 5: /prices serves from KV then from edge cache on repeat ----
  {
    const snapshot = { primary: { a: 1 }, commodity: null, crypto: null, navasan: null, meta: {} };
    const env = { PRICES: makeKv({ snapshot: JSON.stringify(snapshot) }) };
    const cacheStore = makeCacheStore();
    globalThis.caches = cacheStore;

    async function runFetch(req) {
      let pending;
      const ctx = { waitUntil: (p) => { pending = p; } };
      const res = await worker.fetch(req, env, ctx);
      await pending;
      return res;
    }

    const req1 = new Request("https://example.workers.dev/prices");
    const res1 = await runFetch(req1);
    const body1 = await res1.json();
    assert.deepEqual(body1.primary, { a: 1 });
    assert.equal(cacheStore._size(), 1, "first request should populate the edge cache");

    // Second request should be served from cache without touching KV --
    // prove it by deleting the KV row and confirming /prices still works.
    await env.PRICES.put("snapshot", null);
    const req2 = new Request("https://example.workers.dev/prices");
    const res2 = await runFetch(req2);
    const body2 = await res2.json();
    assert.deepEqual(body2.primary, { a: 1 }, "second request should still see cached data, not the wiped KV row");
    console.log("test 5 (edge cache actually shields KV) OK");
  }

  console.log("\nALL WORKER LOGIC TESTS PASSED");
}

run().catch((err) => {
  console.error("TEST FAILED:", err);
  process.exit(1);
});
