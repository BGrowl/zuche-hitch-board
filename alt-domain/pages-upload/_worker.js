/**
 * 神州顺风车车源看板 —— Cloudflare Pages 版透明反代（Advanced Mode）+ 边缘缓存
 *
 * 为什么用 Pages 而不是 Worker：
 *   实测 `*.workers.dev` 在中国大陆被 DNS 污染（解析到 Facebook 的 IP `face:b00c`），
 *   而 `*.pages.dev` 解析正常（Cloudflare 真实 IP），国内可访问。
 *
 * 为什么加缓存：
 *   上游每次回源要 1.5~2.5s（跨境绕行）。看板数据 30 分钟才更新一次，
 *   在 Cloudflare 边缘缓存 60s 无感，但重复打开会从 2.4s 降到 ~0.1s。
 *
 * 部署/更新：
 *   Cloudflare 控制台 → Workers & Pages → 选 zuche-hitch → Create new deployment
 *   → 把这个文件夹整个拖进去 → Deploy（地址不变，仍是 zuche-hitch.pages.dev）
 */

const UPSTREAM = "https://zuche-hitch-board.app.workbuddy.host";
const TTL = 60; // 边缘缓存秒数

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const cacheable = request.method === "GET" && url.pathname !== "/health";
    const cacheKey = new Request(url.toString(), { method: "GET" });

    // 1) 命中边缘缓存直接返回
    if (cacheable) {
      try {
        const hit = await caches.default.match(cacheKey);
        if (hit) {
          const h = new Headers(hit.headers);
          h.set("x-cache", "HIT");
          return new Response(hit.body, { status: hit.status, headers: h });
        }
      } catch (e) { /* 缓存不可用则正常回源 */ }
    }

    // 2) 回源
    const headers = new Headers(request.headers);
    try { headers.delete("host"); } catch (e) { /* Host 是受限头，必须删 */ }

    const init = { method: request.method, headers, redirect: "manual" };
    if (request.method !== "GET" && request.method !== "HEAD") {
      init.body = request.body;
    }

    let resp;
    try {
      resp = await fetch(UPSTREAM + url.pathname + url.search, init);
    } catch (e) {
      return new Response("反代上游失败: " + (e && e.message ? e.message : e), {
        status: 502,
        headers: { "content-type": "text/plain; charset=utf-8" },
      });
    }

    const out = new Headers(resp.headers);
    out.delete("content-security-policy");
    out.delete("content-security-policy-report-only");
    out.delete("x-frame-options");
    out.set("x-cache", "MISS");

    const res = new Response(resp.body, { status: resp.status, headers: out });

    // 3) 写入边缘缓存（带 Set-Cookie 的响应不缓存）
    if (cacheable && resp.status === 200 && !out.has("set-cookie")) {
      const toCache = res.clone();
      toCache.headers.set("Cache-Control", "public, max-age=" + TTL);
      ctx.waitUntil(caches.default.put(cacheKey, toCache).catch(() => {}));
    }

    return res;
  },
};
