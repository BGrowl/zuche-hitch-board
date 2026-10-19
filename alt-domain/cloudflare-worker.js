/**
 * 神州顺风车车源看板 —— 自定义地址（Cloudflare Worker 透明反代）
 *
 * 效果：访问 https://<你的worker名>.<你的账号>.workers.dev 时，
 *       内容实时来自 https://zuche-hitch-board.app.workbuddy.host ，
 *       但**地址栏只显示 workers.dev**，完全看不到 workbuddy。
 *       看板有自己的 30 分钟自动刷新，反代只是换个门牌，数据不会变旧。
 *
 * 部署步骤（全免费，约 2 分钟，无需买域名）：
 *   1. 打开 https://dash.cloudflare.com/sign-up ，用邮箱注册（选 Free 计划）
 *   2. 左侧菜单 Workers & Pages → Create application → Workers → Create Worker
 *   3. 起个名字（例如 zuche-hitch），点 Deploy
 *   4. 点 Edit code，把本文件内容**整个**粘进去替换默认代码，再点 Deploy
 *   5. 拿到地址：https://zuche-hitch.<你的账号>.workers.dev —— 就是它
 *
 * 想换成自己的域名（如 hitch.你的域名.com）：
 *   Worker 页面 → Settings → Domains & Routes → Add → Custom Domain，按提示加即可
 *   （域名需已托管在 Cloudflare，免费计划同样支持）
 */

const UPSTREAM = "https://zuche-hitch-board.app.workbuddy.host";

export default {
  async fetch(request) {
    const url = new URL(request.url);
    const target = UPSTREAM + url.pathname + url.search;

    // 转发请求头（Host 由 fetch 按 target 自动生成，必须删掉原来的）
    const headers = new Headers(request.headers);
    try { headers.delete("host"); } catch (e) { /* ignore */ }

    const init = {
      method: request.method,
      headers,
      redirect: "manual",
    };
    if (request.method !== "GET" && request.method !== "HEAD") {
      init.body = request.body;
    }

    const resp = await fetch(target, init);

    // 复制响应头，并去掉会暴露中转 / 阻止嵌入的几项
    const out = new Headers(resp.headers);
    out.delete("content-security-policy");
    out.delete("content-security-policy-report-only");
    out.delete("x-frame-options");

    return new Response(resp.body, { status: resp.status, headers: out });
  },
};
