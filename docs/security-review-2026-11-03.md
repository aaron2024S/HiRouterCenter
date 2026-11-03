# HiRouterCenter 安全与质量审查报告

> **修复状态（2026-11-03 晚）**：本报告发现的问题已在 1.3.1 全部处理——
> H-1 / H-2 / M-1～M-4 / M-6 / M-7 与 L-1～L-12（M-5 按用户意见收窄为
> 「按 /64 聚合 + 过期清理 + 全局降速不拒登」，设备限速本就是调用路由器设置，
> 与此无关）。每项修复都用审查时的同一套真实服务攻击脚本复验过；
> `tests/test_security_matrix.py` 把权限矩阵、版本一致性、损坏恢复固化为回归测试。

- 审查对象：`D:/workbuddy/HiRouterCenter`（v1.3.0，commit `0b48328`）
- 审查方式：源码走读 + 对**真实服务实例**的可复现验证（不是纯静态推断）
- 审查范围：`app/`（13k 行）+ `Dockerfile` / compose / CI / 测试套件
- 结论：**2 个高危、6 个中危、12 个低危/质量问题**，另有 5 类测试体系缺口

> 说明：本程序定位是"局域网内单用户管理后台"，以下评级已按这个威胁模型折算。
> 但"局域网"不等于可信 —— 同网段的 IoT 设备、被攻陷的 NAS 上其他容器、
> 用户浏览器访问的任意外部网页，都在这个模型内。

---

## P0（高危，建议立即修）

### H-1 改密接口未要求登录，可无限次爆破并直接接管账号

**位置**：`app/webui.py:215`

```python
if method == "POST" and route == "/api/password":
    return self._change_password(handler, body, user, token)   # user 可能为 None
```

该分支位于 `if not user: ... 401` **之前**，也位于同源校验与 Content-Type 校验之前。
`_change_password` 内部只校验 `old` 是否正确，**不使用 `user` 做任何鉴权**。

**实测结果**（`AuthStore` 真实 scrypt 校验，同一进程内模拟 3 个不同来源）：

| 请求 | 结果 |
|---|---|
| `POST /api/login` 连错 8 次 | 第 9 次 `429`（防爆破生效） |
| `POST /api/password` 未登录连错 20 次 | 全部 `400`，**无一次 429** |
| `POST /api/password` 带正确旧密码 | `200 {"ok": true}`（密码被改） |
| 用新密码 `POST /api/login` | `200 {"ok": true}`（**接管成功**） |

**影响**：登录接口的三层防爆破（单 IP 8 次、递进锁定、全局熔断）被完全绕过。
攻击者对 `/api/password` 无限次猜旧密码，一旦命中即把密码改成自己的，随后正常登录。
无需任何已登录会话。

**附带问题**：该路由同时缺 Origin 校验，攻击者网页可用 `fetch(..., {mode:'no-cors'})`
+ `Content-Type: text/plain`（简单请求，不触发预检）盲打，不需要读到响应 ——
命中即改密，之后自己登录即可确认。

**修复**：

```python
if method == "POST" and route == "/api/password":
    if not user:                       # 必须已登录
        return handler.send_json({"ok": False, "error": "未登录"}, 401)
    if not handler.same_origin():      # 必须同源
        return handler.send_json({"ok": False, "error": "跨站请求被拒绝"}, 403)
    if _ctype(handler) != "application/json":
        return handler.send_json({"ok": False, "error": "只接受 application/json"}, 415)
    wait = self._throttled(ip)         # 走同一套限速
    if wait > 0:
        return handler.send_json({"ok": False, "error": "尝试过于频繁"}, 429)
    return self._change_password(handler, body, user, token)
```

另外建议：已登录身份本身即授权，`old` 可作为"二次确认"保留，但失败也要计入
`self._note_fail(ip)`。

---

### H-2 首次初始化可被跨站抢注管理员（CSRF，race to setup）

**位置**：`app/webui.py:193` → `_setup()`（`webui.py:392`）

`/api/setup` 同样在 `if not user`、同源校验、Content-Type 校验**之前**返回。
`_setup` 内部只判断 `setup_done()`，不检查来源。

**实测结果**（模拟浏览器真实形态：`Origin: http://evil.example`、
`Host: 192.168.3.10:6600`、`Content-Type: text/plain`）：

```
初始 setup_done: False
跨站 POST /api/setup -> 200 {'ok': True, 'user': 'pwned'}
setup_done 现在: True
落盘的管理员名: pwned
```

**影响**：容器首次启动、用户还没创建管理员的那段时间窗口内，只要用户的浏览器
访问过任意一个恶意（或含恶意广告/iframe）网页，该网页即可向 `192.168.x.x:6600`
发起 no-cors 请求，把管理员注册成攻击者的账号 —— 用户再打开控制台时，
"创建管理员"入口已永久关闭（403），只能删 `data/auth.json` 重来；若用户没察觉，
攻击者已持有完整控制权（改白名单、关防火墙、重启路由器、看设备列表）。

攻击者需要知道 IP:端口：内网扫描、或 DNS rebinding 把固定域名解析到内网地址，
都可做到。窗口期通常是"部署后到第一次打开网页"之间，恰恰可能很长。

**修复**：`/api/setup` 也必须过同源 + `application/json` 校验；
更稳的做法是**首次初始化绑定一次性令牌** —— 启动时在容器日志里打印
`/api/setup?token=xxxx`，只接受带该令牌的创建请求（本地终端能看到，远程网页拿不到）。
最低成本方案：保留现有体验，但加同源 + ctype 校验，并在日志中提示
"若你未创建管理员却发现入口已关闭，请删除 data/auth.json 后重启"。

---

## P1（中危）

### M-1 用户名存在性时间侧信道（注释与实现相反）

**位置**：`app/auth.py:124`

```python
ok_u = hmac.compare_digest(...)          # 常量时间比较
return bool(ok_u and _verify_hash(...))  # ← 短路：用户名错就不跑 scrypt
```

`webui.py` 顶部注释明确写着："用户名和密码都走同一条比较路径，
不让人从响应快慢里猜出'用户名对不对'" —— **与实际行为相反**。

**实测**（各 7 次平均）：用户名正确 **138.9 ms**，用户名错误 **0.3 ms**（约 460 倍差）。

当前危害被 H-1 之外的另一个问题放大了：`/api/setup-status` **未认证就返回管理员用户名**
（实测 `{"setupDone": true, "username": "admin", ...}`），用户名根本不用猜。
所以这个侧信道眼下价值有限，但一旦修好 M-2，它就会变成可用的用户名枚举手段。

**修复**：用户名不匹配时也跑一次 `_verify_hash`（用固定假记录），让两条路径耗时同量级；
同时 `/api/setup-status` 不再返回 `username`（前端并不需要它）。

### M-2 `/api/setup-status` 未认证泄露管理员用户名

**位置**：`app/webui.py:188`

返回 `username`，但登录页只用 `setupDone`。删掉该字段即可；
若前端确实要显示"请用 xxx 登录"，也应只在已登录会话里返回。

### M-3 凭据文件损坏 → 控制台永久锁死，无任何自救提示

**位置**：`app/auth.py:96` `exists()` 只判断文件存在；`load()` 异常返回 `None`

**实测**（写入半截 JSON，模拟掉电/磁盘满）：

```
GET  /api/setup-status -> 200 {'setupDone': True, 'username': ''}
POST /api/setup        -> 403 「管理员已创建，请直接登录」
POST /api/login        -> 401 「用户名或密码不对」
```

`setupDone` 为真（入口关闭）、`username` 为空、登录永远失败 —— 用户看到的是
"密码不对"，实际是文件坏了。唯一出路是手工 `rm data/auth.json` 重启，而日志里
没有任何"凭据文件读取失败"的明确提示（`load()` 静默吞掉 `ValueError`）。

**修复**：
- `load()` 失败时记 `log.error("凭据文件无法解析（可能损坏）：%s", path)`；
- `setup_done()` 改为"文件存在**且能解析出 username**"，让损坏时能重新初始化，
  或在 `/api/setup-status` 返回 `{"setupDone": true, "broken": true}`，
  前端提示"凭据文件损坏，请删除 data/auth.json 后重启"。

### M-4 连接层无超时、无线程上限（Slowloris）

**位置**：`app/webui.py:532` `class Server(socketserver.ThreadingMixIn, HTTPServer)`

未设置 `timeout`（`BaseHTTPRequestHandler.timeout` 默认 `None`），
`ThreadingMixIn` 未设 `max_children`，每个连接一个线程且永不主动回收。

**实测**：基线 7 线程 → 开 120 个"只发一半请求头"的连接 → **128 线程**（线性增长），
期间正常请求仍可用（说明不是功能 bug，而是资源可被无上限占用）。

**影响**：内网可访问者用几千个半开连接即可耗尽容器内存/线程/文件句柄，
导致控制台不可用（同步线程本身不受影响，属"部分 DoS"）。

**修复**：

```python
class Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True
    request_queue_size = 64          # backlog
    # Handler 侧：
    #   timeout = 15                 # 单连接读超时
    #   max_children = 64            # ThreadingMixIn 的并发上限
```

再配合 `_read_body` 超限时 413 + `Connection: close`。

### M-5 按 IP 限速在 IPv6 环境基本失效，且反向可用来锁死管理员

本应用的主场景就是 IPv6。而 `_throttled()` 以 `client_address[0]` 为键：

- 同一个 /64 前缀下，攻击者可轻松使用海量源地址 → **单 IP 8 次锁定形同虚设**；
- `self._fails` / `self._strikes` **只增不减**（仅登录成功才 `pop`）→ 大量不同源地址
  会让这两个 dict 无限增长（内存慢性泄漏）；
- 兜底的"全局熔断 60 次/5 分钟"反而成了**锁定管理员的工具**：攻击者换 60 个源地址
  故意失败，就能让合法管理员在 5 分钟内完全无法登录（可无限续期）。

**修复建议**：
- 除 IP 外，再按"用户名 + 全局滑动窗口"计数，并对**失败率异常**的来源整体降速；
- 用 `collections.OrderedDict`/定期 GC 清理过期的 `_fails`、`_strikes`；
- 全局熔断改为"仅对未持有有效会话的来源限速"，避免合法会话被牵连；
- 更根本的是：H-1 修好后，攻击面会小很多（改密不再能无限试）。

### M-6 路由器 HTTPS 场景下关闭证书校验

**位置**：`app/router.py:143`

```python
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE
```

路由器默认是 HTTP，当前不影响。但页面允许把「路由器地址」填成 `https://...`，
一旦这么做，任何中间人可劫持会话 cookie（`session.json` 里的 cookie 足以完全控制
路由器：改防火墙、白名单、重启）。密码本身走 SCRAM 不传明文，挡不住会话劫持。

**修复**：对 https 目标至少提供"首次信任指纹"机制，或在文档/界面明确警告；
更简单：`https` 时若证书校验失败，报错并提示改用 `http`，不要静默降级。

### M-7 Dockerfile 镜像版本元数据落后（第 5 处版本声明被漏）

**位置**：`Dockerfile:6`

```dockerfile
org.opencontainers.image.version="1.2.8"
```

而 `app/__init__.py` 已是 `1.3.0`。`docker inspect` / 镜像详情页会显示 1.2.8。
本项目此前认定的"版本号 4 处 + README"实际是 **5 处**：漏了 Dockerfile LABEL。
（1.2.9 → 1.3.0 时未同步。）

**修复**：把 Dockerfile 的 LABEL 加进发版清扫清单；更好的做法是让 CI 用
`--label org.opencontainers.image.version=${{ inputs.tag }}` 覆盖，消除手工同步点。

同时 Dockerfile 里还有一句过时注释：
`# 6600 = 浏览器控制台（未设 ADMIN_PASSWORD 时不监听）` —— 该 env 早已废弃，
实际是 `PORT>0` 就监听。

---

## P2（低危 / 质量）

| # | 位置 | 问题 | 建议 |
|---|---|---|---|
| L-1 | `webui.py:512` | 请求体 >1MB 时 `return b""`，**不读走 body**。HTTP/1.1 keep-alive 下残留字节会被当成下一个请求 → 请求错位 | 返回 413 并 `Connection: close`，或读空丢弃 |
| L-2 | `webui.py:202` | `/api/logout` 无同源校验 → 跨站可强制登出 | 加 `same_origin()`（体验类 CSRF） |
| L-3 | `webui.py:473` | `same_origin()` 比较 `Origin.netloc` 与 `Host` 头，两者都可被攻击者控制（DNS rebinding 场景下同为 `evil.com:6600`）→ 实际防不住 rebinding | 增加 Host 白名单（本机 IP/localhost/配置的域名），或校验 `Sec-Fetch-Site: same-origin` |
| L-4 | `webui.py:384` | Cookie 无 `Secure`、无 `__Host-` 前缀。同机其他端口的服务可覆盖同名 cookie | 反代 HTTPS 时按 `X-Forwarded-Proto` 加 `Secure`；名称改 `__Host-hrc` |
| L-5 | `auth.py:113` | `create()` 的 `exists()` 与 `_write()` 之间无锁 → 并发双创建，后写覆盖 | 用 `os.open(path, O_CREAT|O_EXCL)` 或文件锁做原子占位 |
| L-6 | `settings.py:358` | 通知 URL 只校验 scheme，不限制内网地址（管理员可配，SSRF 面低） | 至少拒绝 `169.254.169.254` 与回环，或明确文档说明 |
| L-7 | `webpage.py:1615` | `escAttr()` 不转义单引号；当前全库属性都用双引号（侥幸安全） | 加 `.replace(/'/g, '&#39;')`，避免将来改单引号时中招 |
| L-8 | `tasks.py:592` | `tasks.json` 未显式 `chmod(0600)`（与 state/settings/auth 不一致）；`.tmp` 为固定名、非 `mkstemp` | 补 `chmod`；用 `mkstemp` |
| L-9 | `sync.py:210` | 密码错误退避 300s→600s→…，**第 3 次仍会去试**，而固件 `maxfailtimes=3` → 用户填错密码后离开，约 15 分钟内把**路由器账号**锁死（需重启路由器） | 连续 2 次 `AuthFailed` 后停止自动重试，改为"等用户在网页里确认/改密码"；容器重启会重置计数，等于绕过退避，需把计数落盘 |
| L-10 | `sync.py:556` + `node.py:476` | `tick()` 全程持 `syncer.lock`（多规则 × 10s 超时，单轮可达数十秒）；期间"立即同步/测试连接/白名单"请求无超时地排队 | 给 `lock` 加超时（`acquire(timeout=5)`），拿不到就返回"正在同步，请稍后" |
| L-11 | `webui.py:99` | 过期 token 只在被访问时清理；`_strikes` 永不淘汰 | 后台定期 GC；或改用 `secrets` + 单会话（单用户场景其实不需要多 token） |
| L-12 | `README.md:204` | 文档称"Origin 与 Host 不一致的 POST 直接 403，且只接受 application/json"，实际 4 条路由（setup/login/password/logout）例外 | 修 H-1/H-2 后文档自然成立；修之前不要这么写 |

---

## 做得对的地方（客观记录）

- 口令 `scrypt(n=2^14,r=8,p=1)` + 每账号独立盐 + `hmac.compare_digest` 校验密码
- `auth.json` / `settings.json` / `state.json` 全部临时文件 + `fsync` + `os.replace` 原子写，0600
- 严格 CSP（`default-src 'none'`、`frame-ancestors 'none'`、`base-uri 'none'`）、
  `X-Content-Type-Options: nosniff`、`Referrer-Policy: no-referrer`、`Cache-Control: no-store`
- **前端转义纪律好**：设备名（局域网内任何设备都能自报任意 HostName，是最现实的存储型
  XSS 载体）在列表/卡片/事件日志里都走了 `escHtml`，`title` 用 DOM 属性赋值而非字符串拼接；
  `toast()` 也做了转义。抽查了 79 处 `innerHTML`，未发现可利用的直出点
- 错误信息不抛内部参数（有 `test_messages_never_leak_internal_params` 锁死），
  异常只进日志
- 容器非 root（uid 10001），健康检查端口只绑 `127.0.0.1`，`/state` 不对外
- 事件/通知历史都有条数上限（200），不会无限写盘
- `ipaddress` 校验 IPv6 并过滤私有地址后才写白名单
- 计划任务有 `KINDS` 白名单、`MAX_TASKS=32`，cron 解析对非法写法全部报错

---

## 测试体系缺口（比单个 bug 更值得修）

442 条用例全绿，却漏掉上面全部问题。根因不是"没测够"，而是**测的地方不对**：

1. **缺"端点 × 身份 × 来源"权限矩阵**。现有用例几乎都"以已登录身份调用正确端点"，
   没人问"未登录能不能调它""跨站能不能调它"。
   建议加表驱动测试：每个 POST 路由 × {未登录, 已登录} × {同源, 跨站} ×
   {json, text/plain, 无 ctype}，断言状态码。H-1/H-2/L-2 会被这张表一次抓出。
2. **安全声明没有对应断言**。`webui.py` 顶部注释写"用户名密码同路径、常量时间"，
   实测差 460 倍。凡是注释/README 声称的安全属性，都应有可执行测试（哪怕只是
   "两条路径耗时比 < 3"这种粗断言）。
3. **缺健壮性/资源类测试**：半开连接、超大 body、损坏的 auth.json、并发 setup、
   `save_settings` 与 `tick` 并发。这类测试最容易被"功能正常"蒙蔽。
4. **缺版本一致性测试**。Dockerfile LABEL 落后 3 个版本无人发现。
   建议一条用例：扫描 `app/__init__.py`、`offline/*.py`、`Dockerfile`、README 标题，
   断言版本串唯一且一致。
5. **缺"文档 vs 实现"的核对**。README 的安全章节是承诺书，应逐条对应到测试。

---

## 建议的修复顺序

1. **H-1、H-2**（一个下午）：`/api/password`、`/api/setup` 归入"需要同源 + ctype"，
   改密再加"必须已登录"与限速；补权限矩阵测试。
2. **M-1、M-2、M-3**（半天）：去掉 `setup-status` 的 username 回显；让 `load()` 报错可见、
   损坏时允许重新初始化。
3. **M-4、L-1**（1 小时）：连接超时、并发上限、413 + close。
4. **M-7 + 版本一致性测试**（30 分钟）：Dockerfile LABEL 与 CI 覆盖。
5. **M-5、M-6、L-9**（设计类，需你确认取舍）：IPv6 限速策略、HTTPS 证书策略、
   路由器账号被锁的保护。
