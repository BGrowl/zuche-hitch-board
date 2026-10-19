/**
 * 神州顺风车车源看板 —— Cloudflare Pages 版透明反代（Advanced Mode）
 *
 * 为什么要用 Pages 而不是 Worker：
 *   实测 `*.workers.dev` 在中国大陆被 DNS 污染（解析到 Facebook 的 IP `face:b00c`），
 *   而 `*.pages.dev` 解析正常（Cloudflare 真实 IP），国内可访问。
 *
 * 部署（用你已有的 Cloudflare 账号，约 3 分钟）：
 *   1. Cloudflare 控制台 → Workers & Pages → Create application
 *   2. 选 Pages 标签 → Upload assets → 项目名填 zuche-hitch
 *   3. 把这个文件夹（含本文件 _worker.js）整个拖进上传框 → Deploy
 *   4. 拿到地址：https://zuche-hitch.pages.dev
 */

const UPSTREAM = "https://zuche-hitch-board.app.workbuddy.host";

export default {
  async fetch(request) {
    const url = new URL(request.url);
    const target = UPSTREAM + url.pathname + url.search;

    const headers = new Headers(request.headers);
    try { headers.delete("host"); } catch (e) { /* ignore */ }

    const init = { method: request.method, headers, redirect: "manual" };
    if (request.method !== "GET" && request.method !== "HEAD") {
      init.body = request.body;
    }

    let resp;
    try {
      resp = await fetch(target, init);
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

    return new Response(resp.body, { status: resp.status, headers: out });
  },
};
