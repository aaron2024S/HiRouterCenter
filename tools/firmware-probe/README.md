# 固件探针工具

用来从华为路由器固件里取证（抓接口返回、挖路由表、导出文案包）。
**只在开发期用，不进 Docker 镜像。**

接口档案（抓到的结论）在 [`../../docs/firmware-api.md`](../../docs/firmware-api.md) ——
**加新功能先去那里查，通常不需要重跑这里的脚本。**

## 环境要求

- Node.js（本机用 `C:\Users\Jun\.workbuddy\binaries\node\versions\22.22.2-6\node.exe`）
- `playwright-core` + 系统里已装的 Edge / Chrome
- 本机能访问路由器管理地址

```bash
export NODE_PATH=/c/Users/Jun/.workbuddy/binaries/node/workspace/node_modules
```

## 四个脚本

| 脚本 | 干什么 | 要不要登录 | 会不会改配置 |
|---|---|---|---|
| `fw-live-grab2.js` | 被动监听：你正常浏览页面，它把固件自己发出的请求响应存下来 | 要 | **不会**（只观察） |
| `fw-crawl.js` | 主动抓：按 `fetch-list.json` 逐个 GET 107 个只读接口 | 要 | **不会**（只发 GET） |
| `fw-reprobe.js` | 复探第一次 404 的关键接口，试几种查询参数变体 | 要 | **不会**（只发 GET） |
| `fw-headers.js` | 请求头矩阵：4 种头组合 × 13 个接口，确认 404 是不是头的问题 | 要 | **不会**（只发 GET） |

**全部脚本都不接触密码**：浏览器弹出来后你自己登录，脚本只复用页面已有的会话。

## 怎么跑

```bash
cd tools/firmware-probe

# 抓全部只读接口（最常用）
node fw-crawl.js

# 只想看某个页面固件发了什么请求
node fw-live-grab2.js
```

浏览器会打开 `http://192.168.3.1/html/index.html`，**手动登录**后脚本自动开始。
结果写到仓库根的 `.tmp-render/fw-live/`（已被 `.gitignore` 排除）。

### 环境变量

| 变量 | 默认 | 说明 |
|---|---|---|
| `HRC_ROUTER` | `http://192.168.3.1` | 路由器地址 |
| `HRC_EDGE` | `C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe` | 浏览器可执行文件 |

## 数据文件

| 文件 | 内容 |
|---|---|
| `routes.json` | 从 `main.js` 提取的 171 条 API 路由（key → path） |
| `fetch-list.json` | 抓取清单：107 个可安全读取 + 64 个有副作用的（附跳过原因） |

改路由表就改 `routes.json`；要放开/收紧哪些接口就改 `fetch-list.json`。

## ⚠️ 安全约定

1. **只发 GET，不发 POST。** 固件的写操作全走 POST，发错了会改配置、重启、甚至恢复出厂。
2. **有副作用的接口一律不发**（`fetch-list.json` 里的 `skip` 段）：重启、升级、恢复出厂、
   上传配置、改密码、诊断、Wi-Fi 扫描、行为上报。
3. **抓到的原始数据含隐私**（MAC、内网 IP、宽带账号、Wi-Fi 名称、序列号），
   只在 `.tmp-render/` 里放着，**不要提交进仓库**。
4. 批量抓时每个请求间隔 250ms。固件对连续快请求会偶发返回 **404 空响应**（不是没这个接口），
   看到「同批次里 200 / 404 交替出现」就是被节流了，隔一会儿重试即可。
