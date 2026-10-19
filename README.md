# 顺风车车源看板（zuche-hitch）

把神州租车 App 里的**顺风车车源**抓下来，做成一个可筛选的网页看板，并在出现合适的新车时推送到微信。

> 个人自用项目，**私有仓库**。含第三方接口逆向细节，请勿公开或分发。

## 它解决什么问题

官方只在 App 内提供顺风车车源列表：不能按车型/档次筛、不能跨城市比价、看到好车全凭刷。这个项目把列表全量落成结构化数据，做到：

- **一屏看完**：全量车源按城市、价格、车型、档次、出行日期筛选；
- **档次自动化**：按品牌 / 车系 / 车身级别算分，分「尊享 / 高级 / 中档 / 入门」四档，好车自动排前面；
- **新车主动找人**：云端每 10 分钟抓一轮，出现新的达标车立刻推微信，另有一条每小时汇总。

## 组成

```
hitch-api        m.zuche.com 网关接口客户端（匿名访问，不带登录态）
refresh.py       抓全量 → 结构化落盘
car_rank.py      档次评分：品牌强制分 > 车型精确匹配 > 品牌兜底 + 车系级别加成
car_class.py     归类：新能源 / 高端车 / 普通车
make_html.py     静态页生成（历史产物，现由 hitch-site/page.html 取代）

hitch-site/      ★ 线上服务（部署单位）
  server.py      标准库 HTTP 服务：/ 、/data.json 、/health；后台线程每 600s 抓一轮
  page.html      前端单页（无外部依赖，纯静态 + fetch data.json）
  push.py        多通道推送：企业微信群机器人 / 微信公众号测试号 / PushPlus / WxPusher
  car_rank.py    与根目录同源，部署时需要
    
alt-domain/      反代 / 备用域名配置（Cloudflare Worker、Vercel）
顺风车-使用说明.md   完整运维手册（接口、限流、推送、排障）
网页端顺风车调研结论.md  为什么网页端/小程序没有车源入口
顺风车接口-解密说明.md   接口加密参数说明
```

## 运行

只需要 Python 3，**无第三方依赖**：

```bash
cd hitch-site
cp push-config.example.json push-config.json   # 填入自己的推送凭据；不填则推送自动跳过
python server.py                                # 默认 8000 端口，PORT 环境变量可改
```

打开 `http://localhost:8000/` 即是看板。

启动后会立即抓一轮，之后每 `REFRESH_SEC`（默认 600 秒）抓一轮。抓取失败只记录错误、不影响页面继续用旧数据。

## 推送

`push.py` 支持四种通道，`push-config.json` 里用 `channel` 选，`auto` 按优先级择一：

企业微信群机器人 → 微信公众号测试号 → PushPlus → WxPusher

- **企业微信群机器人是唯一能做到「文字直接显示在个人微信里」的通道**（配合企业微信「微信插件」）。
  必须用 `text` 类型：官方明确微信插件不支持 markdown，发了只会显示「暂不支持此消息类型」。
- 达门槛：`min_tier = 3` 只推尊享/高级/中档，入门档不打扰。
- 双轨节奏：`pushImmediate` 控制即时推，`push_every_sec` 控制汇总周期（默认 3600 秒）。
- 已推送 id 存在 `push-state.json` 里做去重 —— 该文件不随仓库分发。

## 关于凭据

仓库**不包含任何可用凭据**：

| 文件 | 内容 | 状态 |
|---|---|---|
| `hitch-site/push-config.json` | webhook key、appSecret、PushPlus token | 已忽略，仅提供 `.example` 模板 |
| `hitch-site/push-token.json` | 微信 access_token 缓存 | 已忽略 |
| `h5-cookies.json` / `waf-cookies.json` | 登录态 cookie | 已忽略，且代码默认不使用 |

抓取全程**匿名**。不要给抓取脚本挂登录 cookie：网关的频次限制是按登录会话计的，带上会把账号拖进限流，且重试会延长封禁窗口。

## 许可

All rights reserved. 仅供项目所有者自用，未经许可不得复制、分发或部署。
