# -*- coding: utf-8 -*-
"""
Web 控制台

一个很小的 HTTP 服务，只做两件事：
  1. 用访问密码把入口关起来（首次打开网页时设置，落在 auth.json，
     scrypt 哈希；不用环境变量设密码 —— 环境变量只用于「忘记密码」时的重置）
  2. 提供查看与修改设置的接口，改完热生效，不用重建容器

安全上的取舍（都是有意的，不是漏的）：
  · 单密码模式（参考 dockhelm）：这个控制台只有「管理员」一个角色，登录/创建
    都只问密码。控制台端口只要 PORT>0 就启动；还没设置密码时只开放「设置密码」
    路由，创建成功后该入口永久关闭（403）。「重置」见登录页「忘记密码」说明。
  · 口令存 scrypt 哈希（app/auth.py）。单密码只有一条校验路径，恒定时间问题自然消失。
  · **所有改状态的 POST 一律先过同源 + application/json 校验**，设置密码、
    登录、改密、登出一个不例外（2026-11-03 审查前这几个路由排在鉴权之前，
    未登录就能爆破改密、跨站能抢注管理员）。
  · 登录防爆破（参数设置页可调，存 auth.json 的 lock 字段）：单来源
    （IPv6 按 /64 聚合成一个来源）滑动窗口 5 分钟内连错 N 次（默认 5）即锁定
    M 分钟（默认 5，从触发锁定的那次失败起算）；所有来源合计错 60 次则进入
    "全局限速"（每次校验再多等 2 秒，**不整体拒登** —— 拒登会让攻击者用几十个
    源地址把管理员一起关在门外）；每次登录校验前恒定延时 0.25 秒（拉平响应时间、
    拖慢脚本）。锁定期间密码对也不放行，登录成功即清零。
    失败响应带 remaining（还可尝试几次）、锁定响应带 retryAfter（几秒后解锁），
    前端据此显示「还可尝试 N 次」与锁定倒计时。
  · 会话令牌只放内存（重启即失效），Cookie 带 HttpOnly + SameSite=Lax；
    勾选「保持登录(7天)」时令牌与 Cookie 均按 7 天有效期签发。改密码后其他会话作废。
  · 改状态的请求要求 Content-Type 为 application/json 且 Origin（若有）与 Host 一致
    —— 跨站的 form 表单发不出 application/json（要发就得先过预检，而本服务不响应
    预检），配合 SameSite 足够挡掉 CSRF。需要更严格的来源校验时，用
    WEB_ALLOWED_HOSTS 显式列出允许的 Host（默认接受任意 Host，见 README）。
  · 不监听 0.0.0.0 之外的地址也做不到（容器里必须），所以文档里写明：
    这是**局域网内**的管理后台，别做端口映射到公网。
  · 只走 HTTP 不上 TLS：局域网自签证书更麻烦，且真正敏感的是"谁能访问到这个端口"。
"""
from __future__ import annotations

import hmac
import http.server
import ipaddress
import json
import logging
import os
import secrets
import socketserver
import threading
import time
import urllib.parse

from . import settings as st
from .auth import (WrongPassword as _WrongPassword,
                   FAIL_WINDOW as _FAIL_WINDOW, CONSOLE_USER)
from .node import Busy
from .webpage import PAGE

log = logging.getLogger("ipv6sync.webui")

GLOBAL_FAIL_LIMIT = 60   # 同窗口内全部来源的失败总上限（防换 IP 分摊的分布式猜解）
SLOW_DELAY = 2.0         # 全局压力下的额外延时（不整体拒登，避免误伤管理员）
LOGIN_DELAY = 0.25       # 每次校验前的恒定延时
MAX_BODY = 1 << 20       # 请求体上限（1MB）
MAX_WORKERS = 64         # 并发连接上限

CSP = ("default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; "
       "connect-src 'self'; img-src 'self' data:; form-action 'none'; "
       "frame-ancestors 'none'; base-uri 'none'")


def _rate_key(ip: str) -> str:
    """限速记账键：IPv6 按 /64 前缀聚合。

    本应用的主场景就是 IPv6，而运营商给用户的是整个 /64 —— 一个 /64 里
    换源地址是零成本的，按单个地址记账等于没有限速。IPv4 原样返回。
    """
    try:
        a = ipaddress.ip_address((ip or "").split("%")[0])
    except ValueError:
        return ip or "?"
    if a.version == 6:
        return str(ipaddress.ip_network(f"{a}/64", strict=False))
    return str(a)


def _ctype(handler) -> str:
    return (handler.headers.get("Content-Type") or "").split(";")[0].strip().lower()


class WebUI:
    """控制台 HTTP 服务。

    登录凭据不再来自环境变量：访问密码在**首次打开网页时设置**，落在
    `auth_file`（auth.json，scrypt 哈希）。文件不存在 = 还没初始化，
    只开放「设置密码」路由；设置成功后永久关闭。忘记密码用
    HIROUTERCENTER_PASSWORD 环境变量重置（见 webui_from_env）。
    """

    def __init__(self, node, host: str, port: int, auth_file: str,
                 session_ttl: int = 12 * 3600, allowed_hosts=()):
        from .auth import AuthStore
        self.node = node
        self.host = host
        self.port = port
        self.auth = AuthStore(auth_file)
        pol = self.auth.policy()          # 登录保护：连错几次锁、锁多久
        self._max_failures = pol["max_failures"]
        self._lock_minutes = pol["minutes"]
        self.session_ttl = max(300, int(session_ttl))
        self.REMEMBER_TTL = max(self.session_ttl, 7 * 24 * 3600)  # 保持登录：7 天
        # 允许的 Host（小写，可含端口）。空 = 不限制（默认，兼容"用 IP 直连"
        # 的常规用法与反代/域名访问）；配了之后就只认名单里的来源，
        # 是挡住 DNS rebinding 的唯一可靠手段。
        self.allowed_hosts = tuple(h.strip().lower()
                                   for h in (allowed_hosts or ()) if h.strip())

        self._tokens: dict[str, tuple[str, float]] = {}   # token -> (user, 过期时间)
        self._fails: dict[str, list[float]] = {}          # 来源键 -> [失败时刻]
        self._global_fails: list[float] = []              # 所有来源的失败时刻（全局压力用）
        self._locked_until: dict[str, float] = {}         # 来源键 -> 锁定截止时刻
        self._lock = threading.Lock()
        self._server: http.server.ThreadingHTTPServer | None = None

    # ---------------- 会话 ----------------

    def enabled(self) -> bool:
        return self.port > 0

    def setup_done(self) -> bool:
        """已经创建过管理员，且凭据文件能读出内容。

        只看「文件在不在」会让半截损坏的 auth.json 把控制台永久锁死
        （入口关着、登录永远失败、用户只看到"密码不对"）。损坏时返回
        False，让初始化入口重新开放，由 AuthStore 负责备份旧文件。
        """
        return self.auth.exists() and not self.auth.broken()

    def _check_credentials(self, password: str) -> bool:
        return self.auth.verify(password)

    def _new_token(self, user: str, ttl: int | None = None) -> str:
        tok = secrets.token_urlsafe(32)
        with self._lock:
            now = time.time()
            if len(self._tokens) > 32:
                self._sweep_tokens(now)
            self._tokens[tok] = (user, now + (ttl or self.session_ttl))
        return tok

    def _valid(self, tok: str | None) -> str | None:
        if not tok:
            return None
        with self._lock:
            hit = self._tokens.get(tok)
            if not hit:
                return None
            user, exp = hit
            if exp < time.time():
                self._tokens.pop(tok, None)
                return None
            return user

    def _drop(self, tok: str | None):
        if tok:
            with self._lock:
                self._tokens.pop(tok, None)

    def _throttled(self, ip: str) -> tuple[float, bool]:
        """登录前的闸门。返回 (还需等待的秒数, 是否处于锁定)。

        · 锁定中：密码对了也不放行，等待秒数给前端做倒计时（retryAfter）；
        · 刚出狱：窗口清零重新计数；
        · 全局压力（所有来源合计失败太多）不在这里拦 —— 它只降速不拒登，
          见 _global_pressure / _login 里的 SLOW_DELAY。
        """
        now = time.time()
        key = _rate_key(ip)
        with self._lock:
            self._gc(now)
            until = self._locked_until.get(key, 0.0)
            if until > now:
                return until - now, True
            if until:
                self._locked_until.pop(key, None)
                self._fails.pop(key, None)
        return 0.0, False

    def _note_fail(self, ip: str) -> tuple[bool, int, float]:
        """记一次登录失败。

        返回 (是否触发锁定, 还可尝试几次, 锁定秒数)。触发锁定时顺带把
        _locked_until 立起来 —— 触发锁定的**这一次**直接按「已锁定」回：
        否则前端只会看到「还可尝试 0 次」，下一发请求才被告知锁定，
        语气和时序都对不上（对齐 dockhelm 的行为）。
        """
        now = time.time()
        key = _rate_key(ip)
        with self._lock:
            self._fails.setdefault(key, []).append(now)
            self._global_fails.append(now)
            hist = [t for t in self._fails[key] if now - t < _FAIL_WINDOW]
            self._fails[key] = hist
            n = len(hist)
            if n >= self._max_failures:
                lock = self._lock_minutes * 60
                self._locked_until[key] = now + lock
                log.warning("登录防爆破：%s 在 %.0f 秒内连续失败 %d 次，"
                            "锁定 %d 分钟", ip, _FAIL_WINDOW, n,
                            self._lock_minutes)
                return True, 0, lock
            return False, self._max_failures - n, 0.0

    def _remaining(self, ip: str) -> int:
        """当前窗口内该来源还能尝试几次（给 setup-status 用，不新增失败）。"""
        now = time.time()
        key = _rate_key(ip)
        with self._lock:
            hist = [t for t in self._fails.get(key, []) if now - t < _FAIL_WINDOW]
            return max(self._max_failures - len(hist), 0)

    def _locked_for(self, ip: str) -> float:
        """该来源还需等多少秒才解锁；未锁定返回 0（给 setup-status 用）。"""
        until = self._locked_until.get(_rate_key(ip), 0.0)
        return max(until - time.time(), 0.0)

    def _set_lock_policy(self, failures, minutes) -> dict:
        """更新锁定策略（设置页保存后调用，下一次失败记账立即按新值算）。"""
        pol = self.auth.set_policy(failures, minutes)
        self._max_failures = pol["max_failures"]
        self._lock_minutes = pol["minutes"]
        log.info("登录保护已更新：连错 %d 次锁定 %d 分钟",
                 pol["max_failures"], pol["minutes"])
        return {"maxFailures": self._max_failures, "minutes": self._lock_minutes}

    def _global_pressure(self) -> bool:
        """全局失败量是否已到需要额外降速的程度（不拒登，只拖慢）。"""
        now = time.time()
        with self._lock:
            self._global_fails = [t for t in self._global_fails
                                  if now - t < _FAIL_WINDOW]
            return len(self._global_fails) >= GLOBAL_FAIL_LIMIT

    def _gc(self, now: float) -> None:
        """清理过期记账（调用方必须已持 self._lock）。

        _fails 早期只增不减 —— 换源地址的人能把它们撑成内存泄漏。
        """
        for key in [k for k, v in self._fails.items()
                    if not v or now - v[-1] > _FAIL_WINDOW * 2]:
            self._fails.pop(key, None)
        for key in [k for k, t in self._locked_until.items() if t <= now]:
            # 锁到期（出狱）：窗口一并清零
            self._locked_until.pop(key, None)
            self._fails.pop(key, None)
        if len(self._tokens) > 32:
            self._sweep_tokens(now)

    def _sweep_tokens(self, now: float | None = None) -> None:
        """清掉过期会话（调用方必须已持 self._lock）。"""
        now = now if now is not None else time.time()
        for tok in [t for t, (_, exp) in self._tokens.items() if exp <= now]:
            self._tokens.pop(tok, None)

    def _clear_fails(self, ip: str):
        key = _rate_key(ip)
        with self._lock:
            self._fails.pop(key, None)
            self._locked_until.pop(key, None)

    # ---------------- 路由 ----------------

    def _reject_bad_post(self, handler) -> bool:
        """改状态请求的两道门：同源 + application/json。

        返回 True 表示已经回包（请求被拒），调用方直接 return。
        只收 application/json 是有意的：跨站 form 发不出这个类型，
        fetch 想发就得先过 CORS 预检，而本服务不响应预检。
        """
        if not handler.same_origin():
            handler.send_json(
                {"ok": False, "error": "跨站请求被拒绝（来源与本机地址不一致）"}, 403)
            return True
        if _ctype(handler) != "application/json":
            handler.send_json({"ok": False, "error": "只接受 application/json"}, 415)
            return True
        return False

    def _cookie(self, tok: str, max_age: int, secure: bool = False) -> str:
        parts = [f"ipv6sync_web={tok}", "Path=/", "HttpOnly", "SameSite=Lax",
                 f"Max-Age={max_age}"]
        if secure:
            parts.append("Secure")
        return "; ".join(parts)

    def handle(self, handler: "Handler", method: str, path: str, body: bytes):
        q = urllib.parse.urlparse(path)
        route = q.path.rstrip("/") or "/"
        ip = handler.client_address[0]

        # 静态页面不需要登录（登录表单本身就在里面）
        if method == "GET" and route in ("/", "/index.html"):
            return handler.send_bytes(200, PAGE.replace(
                "__APP_VERSION__", _version()).encode("utf-8"),
                "text/html; charset=utf-8", csp=True)

        if method == "GET" and route == "/api/version":
            return handler.send_json({"name": "HiRouterCenter",
                                      "version": _version()})

        # ---- 初始化：只在「还没有密码」时开放，设置成功后永久关闭 ----
        if method == "GET" and route == "/api/setup-status":
            # 不回显任何凭据。failures / lockedFor 是给登录页的：
            # 刷新后「还可尝试 N 次」和锁定倒计时都能接上（对齐 dockhelm）。
            return handler.send_json({"setupDone": self.setup_done(),
                                      "broken": self.auth.broken(),
                                      "version": _version(),
                                      "maxFailures": self._max_failures,
                                      "failures": self._remaining(ip),
                                      "lockedFor": round(self._locked_for(ip))})

        # ---- 登录前的三个动作：先过来源与类型校验，再谈业务 ----
        # 顺序很关键：这几条排在鉴权之前（本来也没法鉴权），所以必须自己
        # 把关，否则跨站页面能直接抢注管理员、未登录就能爆破改密。
        if method == "POST" and route in ("/api/setup", "/api/login", "/api/logout"):
            if self._reject_bad_post(handler):
                return
            if route == "/api/setup":
                return self._setup(handler, body, ip)
            if route == "/api/login":
                return self._login(handler, body, ip)
            self._drop(handler.cookie("ipv6sync_web"))
            handler.send_json({"ok": True}, extra_headers=[
                ("Set-Cookie", self._cookie("", 0))])
            return

        token = handler.cookie("ipv6sync_web")
        user = self._valid(token)

        if method == "GET" and route == "/api/session":
            # version 一并返回：登录页页脚要显示「HiRouterCenter x.y.z」，
            # 而 boot()（里面才拉 /api/version）要等登录后才跑。
            # broken = 凭据文件损坏、入口已重新打开，前端要如实告诉用户。
            # lock = 当前登录保护策略，设置页「控制台账号」卡要显示。
            return handler.send_json({"authed": bool(user), "user": user or "",
                                      "setupDone": self.setup_done(),
                                      "broken": self.auth.broken(),
                                      "version": _version(),
                                      "lock": {"maxFailures": self._max_failures,
                                               "minutes": self._lock_minutes}})

        if not user:
            # 未登录：状态类接口温和地回 authed=false，动作类接口直接 401
            if route in ("/api/state",):
                return handler.send_json({"authed": False})
            return handler.send_json({"ok": False, "error": "未登录"}, 401)

        if method == "GET" and route == "/api/state":
            return handler.send_json({
                "authed": True, "user": user,
                "overview": self.node.overview(),
                "settings": self.node.settings_view(),
                "status": self.node.snapshot(),
            })

        # ---- 以下都是改状态的动作，要求同源 + application/json ----
        if method == "POST" and self._reject_bad_post(handler):
            return

        # 改密：必须已登录（上面刚拦过）+ 走同一套限速。
        # 位置很关键 —— 早期版本这条排在 `if not user` 之前，且内部只看 old，
        # 于是未登录就能无限次猜旧密码，猜中即改密接管（2026-11-03 审查 H-1）。
        if method == "POST" and route == "/api/password":
            wait, locked = self._throttled(ip)
            if locked:
                return handler.send_json(
                    {"ok": False, "locked": True, "retryAfter": round(wait),
                     "error": f"尝试过于频繁，请约 {int(wait) // 60 + 1} 分钟后再试"}, 429)
            res = self._change_password(handler, body, user, token)
            if res is False:          # 旧密码不对：计入同一个失败账本
                locked2, remaining, _ = self._note_fail(ip)
                return handler.send_json(
                    {"ok": False, "error": "当前密码不正确"
                     + (f"，还可尝试 {remaining} 次" if not locked2 else "")},
                    400)
            return

        # 登录保护策略：连错几次锁、锁多久（存 auth.json 的 lock 字段）
        if method == "POST" and route == "/api/auth/lock-policy":
            try:
                data = _json_body(body)
            except ValueError as e:
                return handler.send_json({"ok": False, "error": str(e)}, 400)
            pol = self._set_lock_policy(data.get("max_failures"),
                                        data.get("minutes"))
            return handler.send_json({"ok": True, "lock": pol})

        try:
            if method == "POST" and route == "/api/settings":
                patch = _json_body(body)
                res = self.node.save_settings(patch)
                res["ok"] = True
                return handler.send_json(res)
            if method == "POST" and route == "/api/sync":
                snap = self.node.sync_now()
                return handler.send_json({"ok": snap.get("ok", True), "state": snap})
            if method == "POST" and route == "/api/router/test":
                return handler.send_json(self.node.test_connection())
            if method == "GET" and route == "/api/router/whitelist":
                return handler.send_json(self.node.whitelist())
            if method == "GET" and route == "/api/router/hosts":
                return handler.send_json(self.node.hosts())
            # 轻量：只读 HostInfo，只为设备卡上的实时速率/在线时长（设备页每 5 秒一次）
            if method == "GET" and route == "/api/router/traffic":
                return handler.send_json(self.node.traffic())
            if method == "POST" and route == "/api/wol":
                res = self.node.wake_device(_json_body(body))
                # 限频回 429：前端据此知道是「刚发过」而不是真失败
                return handler.send_json(res, 429 if res.get("throttled") else 200)
            if method == "POST" and route == "/api/router/firewall":
                data = _json_body(body)
                want = data.get("enable")
                if not isinstance(want, bool):
                    return handler.send_json(
                        {"ok": False, "error": "enable 必须是 true/false"}, 400)
                return handler.send_json(self.node.set_firewall(want))
            if method == "POST" and route == "/api/counters/reset":
                return handler.send_json(self.node.reset_counters())
            if method == "GET" and route == "/api/events":
                return handler.send_json(self.node.events_list())
            if method == "POST" and route == "/api/events/clear":
                return handler.send_json(self.node.events_clear())
            if method == "POST" and route == "/api/events/max":
                return handler.send_json(self.node.set_events_max(
                    _json_body(body).get("max")))
            if method == "POST" and route == "/api/rules":
                return handler.send_json(self.node.rules_api(_json_body(body)))
            if method == "POST" and route == "/api/router/whitelist/delete":
                return handler.send_json(
                    self.node.delete_whitelist_entry(_json_body(body)))
            if method == "POST" and route == "/api/router/whitelist/update":
                return handler.send_json(
                    self.node.update_whitelist_entry(_json_body(body)))
            if method == "POST" and route == "/api/notify/test":
                return handler.send_json(self.node.test_notify())
            # ---- 通知：渠道 / 事件订阅 / 策略 / 推送历史 ----
            if method == "GET" and route == "/api/notify":
                return handler.send_json(self.node.notify_view())
            if method == "POST" and route == "/api/notify/channels":
                return handler.send_json(
                    self.node.save_channels(_json_body(body).get("channels")))
            if method == "POST" and route == "/api/notify/channel/test":
                return handler.send_json(
                    self.node.test_channel(_json_body(body).get("channel") or {}))
            if method == "POST" and route == "/api/notify/policy":
                return handler.send_json(
                    self.node.save_notify_policy(_json_body(body)))
            if method == "GET" and route == "/api/notify/history":
                return handler.send_json(self.node.notify_history())
            if method == "POST" and route == "/api/notify/history/clear":
                return handler.send_json(self.node.clear_notify_history())
            if method == "POST" and route == "/api/notify/dedupe/reset":
                return handler.send_json(self.node.reset_notify_dedupe())
            # ---- 路由器信息卡 / 快捷操作 / 设备类型 ----
            if method == "GET" and route == "/api/router/info":
                return handler.send_json(self.node.router_info())
            if method == "POST" and route == "/api/router/action":
                data = _json_body(body)
                return handler.send_json(self.node.router_action(
                    data.get("kind"), data.get("value")))
            if method == "GET" and route == "/api/host/types":
                from . import devtypes
                return handler.send_json({"ok": True, "types": [
                    {"id": t, "name": n} for t, n in devtypes.TYPES]})
            if method == "POST" and route == "/api/host/type":
                data = _json_body(body)
                return handler.send_json(self.node.set_host_type(
                    data.get("mac"), data.get("type")))
            # ---- 设备卡三个动作：改名 / 限速 / 黑名单 ----
            if method == "POST" and route == "/api/host/rename":
                data = _json_body(body)
                return handler.send_json(self.node.rename_host(
                    data.get("mac"), data.get("name")))
            if method == "POST" and route == "/api/host/limit":
                data = _json_body(body)
                return handler.send_json(self.node.set_host_limit(
                    data.get("mac"), data.get("up_kbps") or 0,
                    data.get("down_kbps") or 0))
            if method == "POST" and route == "/api/host/blacklist":
                data = _json_body(body)
                return handler.send_json(self.node.set_host_blacklist(
                    data.get("mac"), bool(data.get("on", True))))
            # ---- 计划任务（读不需要动作，写全部要求登录 + 同源，已在上方拦过） ----
            if method == "GET" and route == "/api/tasks":
                return handler.send_json(self.node.tasks_view())
            if method == "POST" and route == "/api/tasks/cron_check":
                return handler.send_json(
                    self.node.task_cron_check(_json_body(body)))
            if method == "POST" and route == "/api/tasks/save":
                return handler.send_json(self.node.task_save(_json_body(body)))
            if method == "POST" and route == "/api/tasks/delete":
                return handler.send_json(self.node.task_delete(_json_body(body)))
            if method == "POST" and route == "/api/tasks/toggle":
                return handler.send_json(self.node.task_toggle(_json_body(body)))
            if method == "POST" and route == "/api/tasks/run":
                return handler.send_json(self.node.task_run(_json_body(body)))
        except st.SettingsError as e:
            return handler.send_json({"ok": False, "error": str(e)}, 400)
        except Busy:
            # 同步正跑着（一轮可能几十秒）。回 409 让前端提示"稍后再点"，
            # 比让请求挂到浏览器超时好得多。
            return handler.send_json(
                {"ok": False, "error": "正在同步，请过几秒再试"}, 409)
        except Exception:  # noqa: BLE001
            # 异常类名与原始错误只进日志 —— 界面上不出现任何内部参数
            log.exception("控制台接口 %s 出错", route)
            return handler.send_json(
                {"ok": False, "error": "服务器内部出错，请稍后重试"}, 500)

        return handler.send_json({"ok": False, "error": "not found"}, 404)

    def _login(self, handler: "Handler", body: bytes, ip: str):
        wait, locked = self._throttled(ip)
        if locked:
            return handler.send_json(
                {"ok": False, "locked": True,
                 "error": f"登录失败次数过多，请约 {int(wait) // 60 + 1} 分钟后再试",
                 "retryAfter": round(wait)}, 429)
        try:
            data = _json_body(body)
        except ValueError as e:
            return handler.send_json({"ok": False, "error": str(e)}, 400)

        # 恒定延时：拉平正确/错误口令的响应时间，也拖慢脚本化尝试。
        # 全局失败量偏高时再多等一会儿 —— 只降速、不拒登。
        delay = LOGIN_DELAY
        if self._global_pressure():
            delay += SLOW_DELAY
        time.sleep(delay)

        # 单密码模式：请求里就算带了历史遗留的 user 字段也直接忽略
        if self._check_credentials(str(data.get("password", ""))):
            self._clear_fails(ip)
            ttl = self.REMEMBER_TTL if data.get("remember") else self.session_ttl
            tok = self._new_token(self.auth.username(), ttl)
            log.info("控制台登录成功，来源 %s（会话 %s）",
                     ip, "7天" if data.get("remember") else f"{self.session_ttl // 3600}小时")
            return handler.send_json(
                {"ok": True, "user": self.auth.username()},
                extra_headers=[("Set-Cookie",
                                self._cookie(tok, ttl, handler.forwarded_https()))])

        locked2, remaining, lock_secs = self._note_fail(ip)
        if locked2:
            # 触发锁定的这一次就按「已锁定」回：别让前端先看到「还可尝试 0 次」，
            # 下一发请求才被告知 429 —— 时序和语气都对不上。
            return handler.send_json(
                {"ok": False, "locked": True,
                 "error": f"连续 {self._max_failures} 次密码错误，已锁定"
                          f" {self._lock_minutes} 分钟",
                 "retryAfter": round(lock_secs)}, 429)
        log.warning("控制台登录失败，来源 %s（还剩 %d 次机会）", ip, remaining)
        return handler.send_json(
            {"ok": False, "error": "密码错误", "remaining": remaining}, 401)

    def _setup(self, handler, body: bytes, ip: str):
        """首次设置访问密码（单密码，不再有用户名）。只允许一次：
        auth.json 存在后这里永远 403。

        凭据文件损坏时（半截 JSON / 空文件）允许重建 —— 否则控制台会永久
        锁死：入口关着、登录又永远失败，用户只看到"密码不对"。
        """
        if self.setup_done():
            return handler.send_json(
                {"ok": False, "error": "密码已设置，请直接登录"}, 403)
        try:
            data = _json_body(body)
        except ValueError as e:
            return handler.send_json({"ok": False, "error": str(e)}, 400)
        if str(data.get("password", "")) != str(data.get("password2", "")):
            return handler.send_json({"ok": False, "error": "两次输入的密码不一致"}, 400)
        try:
            self.auth.create(str(data.get("password", "")))
        except ValueError as e:            # AuthError：密码强度问题
            return handler.send_json({"ok": False, "error": str(e)}, 400)
        except OSError as e:
            log.error("写入 auth.json 失败：%s", e)
            return handler.send_json(
                {"ok": False, "error": "凭据写入失败，请检查 data 目录权限"}, 500)
        log.info("访问密码已设置（来源 %s）—— 初始化入口从此关闭", ip)
        tok = self._new_token(CONSOLE_USER, self.session_ttl)
        return handler.send_json(
            {"ok": True, "user": CONSOLE_USER},
            extra_headers=[("Set-Cookie",
                            self._cookie(tok, self.session_ttl,
                                         handler.forwarded_https()))])

    # ---------------- 启动 ----------------

    def _change_password(self, handler, body: bytes, user: str, token: str):
        """已登录改密。成功后作废**其他**会话（当前浏览器不掉线）。

        返回 False 表示"旧密码不对"（调用方要把它计入失败账本）；
        其余情况已经自己回包，返回 None。
        """
        try:
            data = _json_body(body)
        except ValueError as e:
            return handler.send_json({"ok": False, "error": str(e)}, 400)
        try:
            self.auth.update_password(str(data.get("old", "")),
                                      str(data.get("new", "")))
        except _WrongPassword:             # 旧密码不对：交给调用方记账
            return False
        except ValueError as e:            # AuthError：新密码太弱等
            return handler.send_json({"ok": False, "error": str(e)}, 400)
        except OSError as e:
            log.error("写 auth.json 失败：%s", e)
            return handler.send_json(
                {"ok": False, "error": "凭据写入失败，请检查 data 目录权限"}, 500)
        with self._lock:
            now = time.time()
            for tok in [t for t, (_, exp) in self._tokens.items()
                        if t != token and exp > now]:
                self._tokens.pop(tok, None)
        log.info("控制台密码已修改（用户 %s），其他会话已作废", user)
        return handler.send_json({"ok": True})

    def start(self) -> http.server.ThreadingHTTPServer | None:
        if self.port <= 0:
            log.info("Web 控制台已关闭（PORT=0）")
            return None
        if not self.setup_done():
            log.info("首次启动：还没设置访问密码。浏览器打开控制台即可设置"
                     "（入口只在这一刻开放，之后永久关闭）")
        else:
            log.info("Web 控制台已就绪（登录保护：连错 %d 次锁定 %d 分钟）",
                     self._max_failures, self._lock_minutes)

        ui = self

        class Handler(http.server.BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"
            server_version = "ipv6sync-console/" + _version()
            # 单连接读写超时：没有它，几千个"只发一半请求头"的连接就能把
            # 线程和文件句柄吃干净（Slowloris）。见审查报告 M-4。
            timeout = 20

            def log_message(self, fmt, *args):
                log.debug("%s - %s", self.client_address[0], fmt % args)

            # ---- 小工具 ----
            def cookie(self, name: str) -> str | None:
                raw = self.headers.get("Cookie") or ""
                for part in raw.split(";"):
                    k, _, v = part.strip().partition("=")
                    if k == name:
                        return v
                return None

            def same_origin(self) -> bool:
                """来源校验：Origin 与 Host 一致，且 Host 在允许名单内（若配了）。

                只比 Origin 与 Host 是可被 DNS rebinding 绕过的（两者的域名
                都由攻击者控制）；配了 WEB_ALLOWED_HOSTS 之后才有真正的边界。
                """
                host = (self.headers.get("Host") or "").lower()
                if ui.allowed_hosts and host not in ui.allowed_hosts:
                    log.warning("拒绝未在允许名单内的 Host：%s", host)
                    return False
                origin = self.headers.get("Origin")
                if not origin:
                    return True          # 非浏览器客户端不带 Origin
                try:
                    o = urllib.parse.urlparse(origin)
                except ValueError:
                    return False
                if (o.netloc or "").lower() != host:
                    return False
                # 现代浏览器都会带 Sec-Fetch-Site；带了就必须是同源，
                # 这是浏览器自己盖章的，页面脚本改不了。
                sfs = (self.headers.get("Sec-Fetch-Site") or "").lower()
                if sfs and sfs not in ("same-origin", "none"):
                    return False
                return True

            def forwarded_https(self) -> bool:
                """是否经 HTTPS 反代访问（决定 cookie 要不要加 Secure）。"""
                return (self.headers.get("X-Forwarded-Proto") or "").lower() == "https"

            def _headers_common(self, code, ctype, length, csp=False,
                                extra=()):
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(length))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("Referrer-Policy", "no-referrer")
                if csp:
                    self.send_header("Content-Security-Policy", CSP)
                for k, v in extra:
                    self.send_header(k, v)
                self.end_headers()

            def send_bytes(self, code, payload: bytes, ctype: str,
                           csp: bool = False, extra=()):
                try:
                    self._headers_common(code, ctype, len(payload), csp, extra)
                    self.wfile.write(payload)
                except (BrokenPipeError, ConnectionResetError,
                        ConnectionAbortedError):
                    pass

            def send_json(self, obj, code: int = 200, extra_headers=()):
                body = json.dumps(obj, ensure_ascii=False, indent=1).encode("utf-8")
                self.send_bytes(code, body, "application/json; charset=utf-8",
                                extra=extra_headers)

            def _read_body(self) -> bytes | None:
                """读请求体。超限返回 None（调用方回 413 并关连接）。

                早期版本超限时直接 `return b""` 却不把字节读走 ——
                keep-alive 下残留的字节会被当成下一个请求的开头，请求错位。
                """
                try:
                    n = int(self.headers.get("Content-Length") or 0)
                except ValueError:
                    n = 0
                if n <= 0:
                    return b""
                if n > MAX_BODY:
                    return None
                return self.rfile.read(n)

            def do_GET(self):
                ui.handle(self, "GET", self.path, b"")

            def do_POST(self):
                body = self._read_body()
                if body is None:
                    self.close_connection = True     # 不读完就不复用这条连接
                    self.send_json({"ok": False,
                                    "error": "请求体过大（上限 1MB）"}, 413,
                                   extra_headers=[("Connection", "close")])
                    return
                ui.handle(self, "POST", self.path, body)

            def do_HEAD(self):
                self.send_error(405)

        class Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
            daemon_threads = True
            allow_reuse_address = True
            request_queue_size = 64

            def __init__(self, *a, **kw):
                super().__init__(*a, **kw)
                # 并发线程上限：ThreadingMixIn 自己没有 max_children，
                # 不设的话每个连接一个线程且没有上界。
                self._slots = threading.BoundedSemaphore(MAX_WORKERS)

            def process_request(self, request, client_address):
                if not self._slots.acquire(blocking=False):
                    try:
                        request.sendall(b"HTTP/1.1 503 Service Unavailable\r\n"
                                        b"Content-Length: 0\r\n"
                                        b"Retry-After: 5\r\n"
                                        b"Connection: close\r\n\r\n")
                    except OSError:
                        pass
                    self.shutdown_request(request)
                    return
                try:
                    super().process_request(request, client_address)
                except Exception:
                    self._slots.release()
                    raise

            def process_request_thread(self, request, client_address):
                try:
                    super().process_request_thread(request, client_address)
                finally:
                    self._slots.release()

        try:
            srv = Server((self.host, self.port), Handler)
        except OSError as e:
            log.error("Web 控制台端口 %d 绑定失败：%s", self.port, e)
            return None
        self._server = srv
        t = threading.Thread(target=srv.serve_forever, name="webui", daemon=True)
        t.start()
        log.info("Web 控制台已监听 %s:%d —— 浏览器打开 http://<本机IP>:%d/",
                 self.host, self.port, self.port)
        return srv

    def stop(self):
        if self._server:
            try:
                self._server.shutdown()
            except Exception:  # noqa: BLE001
                pass


def _json_body(body: bytes) -> dict:
    if not body:
        return {}
    try:
        data = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise ValueError(f"请求体不是合法 JSON: {e}")
    if not isinstance(data, dict):
        raise ValueError("请求体必须是 JSON 对象")
    return data


def _version() -> str:
    from . import __version__
    return __version__


def webui_from_env(node, **overrides) -> WebUI:
    """按环境变量装配控制台。

    登录密码**平时不走环境变量**：在首次打开网页时设置，落在 auth.json。
    唯一的例外是 HIROUTERCENTER_PASSWORD —— 「忘记密码」的兜底之一：
    设上它重启容器，密码被无条件覆盖成这个值（用完记得删掉再重启，
    否则每次启动都会重置；设置页改密码也拦不住它）。
    文件位置可用 AUTH_FILE 覆盖，默认与 SETTINGS_FILE 同目录（都在卷里）。
    """
    def env(name, default=""):
        v = os.environ.get(name)
        return default if v in (None, "") else v

    def env_int(name, default):
        try:
            return int(env(name, str(default)))
        except ValueError:
            log.warning("%s 不是整数，回退到 %s", name, default)
            return default

    host = overrides.get("host") or env("WEB_HOST", "0.0.0.0")
    port = overrides.get("port") or env_int("PORT", 6600)
    settings_file = env("SETTINGS_FILE", "/data/settings.json")
    auth_file = (overrides.get("auth_file") or env("AUTH_FILE")
                 or os.path.join(os.path.dirname(settings_file), "auth.json"))
    ttl = env_int("WEB_SESSION_TTL", 12 * 3600)
    # WEB_ALLOWED_HOSTS：逗号分隔的 Host 白名单（含端口，如 192.168.3.10:6600）。
    # 不配 = 不限（默认，兼容用 IP / 域名 / 反代访问的常规用法）。
    allowed = tuple(h.strip() for h in env("WEB_ALLOWED_HOSTS").split(",") if h.strip())
    ui = WebUI(node, host, port, auth_file, ttl, allowed_hosts=allowed)

    # 忘记密码兜底：环境变量重置。放这里是因为 AUTH_FILE 可被覆盖，
    # 重置必须打在控制台真正用的那份凭据文件上。
    force = os.environ.get("HIROUTERCENTER_PASSWORD", "")
    if force:
        try:
            ui.auth.set_password(force)
            log.info("已按 HIROUTERCENTER_PASSWORD 重置控制台密码"
                     "（建议现在就删掉这个环境变量再重启，"
                     "否则每次启动都会把密码改回去）")
        except ValueError as e:
            log.warning("HIROUTERCENTER_PASSWORD 不满足密码要求，未重置：%s", e)
        except OSError as e:
            log.error("按 HIROUTERCENTER_PASSWORD 重置密码失败：%s", e)
    return ui
