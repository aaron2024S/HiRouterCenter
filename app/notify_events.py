# -*- coding: utf-8 -*-
"""
通知事件模型：**事件代码 → 标题**，外加投递策略（静默时段 / 去重）与推送历史。

为什么要这层：以前的推送是「白名单变了 → 发一句 'IPv6 白名单已更新'」，
标题写死在一个输入框里，用户得自己想措辞。现在标题按事件写死在下面这张表里，
用户只需要决定「哪些事件要推」。

三类东西都在这里：
  · EVENT 表 —— 事件代码、分组、推送标题、等级、默认是否开启
  · 策略 —— 总开关 / 静默时段 / 同事件去重窗口
  · 历史 —— /data/notify.jsonl，一行一条投递结果，按保留条数裁最旧的

投递失败**永不抛异常**：通知只是锦上添花，绝不能影响同步主流程。
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time

from . import notify

log = logging.getLogger("ipv6sync.notify_events")

# 推送历史保留条数的可选值与上限（界面上是个下拉）
HISTORY_CHOICES = (50, 100, 150, 200)
HISTORY_MAX_LIMIT = 200
HISTORY_DEFAULT = 50

# 静默时段里照常发送的等级
LEVEL_URGENT = "urgent"
LEVEL_NORMAL = "normal"

# --------------------------------------------------------------------------
# 事件表：code, 分组, 推送标题, 等级, 默认开启
# 标题都是短句（10 个汉字内），手机通知栏不会被截。
# --------------------------------------------------------------------------
EVENTS: tuple = (
    # --- IPv6 防火墙 ---
    ("fw_add",     "IPv6 防火墙", "已加入 IPv6 白名单",   LEVEL_NORMAL, True),
    ("fw_update",  "IPv6 防火墙", "设备 IPv6 已更新",     LEVEL_NORMAL, True),
    ("fw_remove",  "IPv6 防火墙", "已从 IPv6 白名单移除", LEVEL_NORMAL, False),
    ("fw_off",     "IPv6 防火墙", "IPv6 防火墙被关闭",    LEVEL_URGENT, True),
    ("fw_fail",    "IPv6 防火墙", "IPv6 同步失败",        LEVEL_URGENT, True),
    # --- 设备 ---
    ("dev_online", "设备", "设备已上线",       LEVEL_NORMAL, True),
    ("dev_offline", "设备", "设备已离线",      LEVEL_NORMAL, True),
    ("dev_new",    "设备", "发现新设备接入",   LEVEL_NORMAL, False),
    ("dev_blocked", "设备", "设备已被拉黑",    LEVEL_NORMAL, False),
    # --- 计划任务 ---
    ("task_ok",    "计划任务", "计划任务执行成功", LEVEL_NORMAL, True),
    ("task_fail",  "计划任务", "计划任务执行失败", LEVEL_URGENT, False),
    ("task_miss",  "计划任务", "计划任务已错过",   LEVEL_NORMAL, False),
    # --- 系统 ---
    ("sys_unreachable", "系统", "连不上路由器",   LEVEL_URGENT, True),
    ("sys_login_fail",  "系统", "路由器登录失败", LEVEL_URGENT, False),
)

EVENT_BY_CODE = {e[0]: e for e in EVENTS}
EVENT_GROUPS = tuple(dict.fromkeys(e[1] for e in EVENTS))

# 语气 → 标题图标（与 dockhelm 同一套）：推送标题一眼看出好坏，不用点开读正文。
# 纯文本渠道（钉钉/企业微信这类）不剥离，图标随标题一起发；邮件主题由
# EmailMessage 自动做 RFC2047 编码，emoji 也没问题。
TONE_ICON = {"success": "✅", "failed": "❌", "warning": "⚠️", "info": "ℹ️"}

# 事件 → 语气。写进 EVENT 表的 code 就得在这里配语气，漏配的按 info 处理。
EVENT_TONE = {
    "fw_add":          "success",   # 加白成功
    "fw_update":       "success",   # 地址更新成功
    "fw_remove":       "info",      # 移除是正常操作，不算坏事
    "fw_off":          "warning",   # 防火墙被关闭：状态异常但不是程序故障
    "fw_fail":         "failed",
    "dev_online":      "success",
    "dev_offline":     "warning",
    "dev_new":         "info",
    "dev_blocked":     "warning",
    "task_ok":         "success",
    "task_fail":       "failed",
    "task_miss":       "warning",
    "sys_unreachable": "failed",
    "sys_login_fail":  "failed",
    "test":            "info",
}


def icon_of(code: str) -> str:
    """事件在推送标题前的图标；陌生代码一律 ℹ️。"""
    return TONE_ICON.get(EVENT_TONE.get(code), TONE_ICON["info"])


def events_table(cfg) -> list[dict]:
    """给界面用的事件清单（带当前开关状态）。"""
    over = getattr(cfg, "notify_events", None) or {}
    out = []
    for code, group, title, level, default in EVENTS:
        on = bool(over.get(code, default))
        out.append({"code": code, "group": group, "title": title,
                    "level": level, "default": default, "on": on})
    return out


def default_events() -> dict:
    return {e[0]: e[4] for e in EVENTS}


def normalize_events(raw) -> dict:
    """只接受事件表里认识的代码，值是布尔。未知代码丢弃（不写进设置文件）。"""
    if not isinstance(raw, dict):
        return {}
    return {k: bool(v) for k, v in raw.items() if k in EVENT_BY_CODE}


def event_enabled(cfg, code: str) -> bool:
    over = getattr(cfg, "notify_events", None) or {}
    if code in over:
        return bool(over[code])
    e = EVENT_BY_CODE.get(code)
    return bool(e[4]) if e else False


def title_of(code: str, fallback: str = "通知") -> str:
    e = EVENT_BY_CODE.get(code)
    return e[2] if e else fallback


def level_of(code: str) -> str:
    e = EVENT_BY_CODE.get(code)
    return e[3] if e else LEVEL_NORMAL


# --------------------------------------------------------------------------
# 静默时段
# --------------------------------------------------------------------------

def parse_quiet(raw: str) -> tuple[int, int] | None:
    """'23:00-07:00' → (1380, 420)。空串 / 格式不对 → None（= 不静默）。"""
    s = (raw or "").strip()
    if not s or "-" not in s:
        return None
    a, b = s.split("-", 1)
    try:
        ah, am = [int(x) for x in a.strip().split(":")]
        bh, bm = [int(x) for x in b.strip().split(":")]
    except (ValueError, TypeError):
        return None
    if not (0 <= ah <= 23 and 0 <= bh <= 23 and 0 <= am <= 59 and 0 <= bm <= 59):
        return None
    return ah * 60 + am, bh * 60 + bm


def in_quiet(raw: str, now: float | None = None) -> bool:
    """当前是否处在静默时段（支持跨零点，如 23:00-07:00）。"""
    rng = parse_quiet(raw)
    if not rng:
        return False
    start, end = rng
    if start == end:
        return False
    t = time.localtime(now if now is not None else time.time())
    cur = t.tm_hour * 60 + t.tm_min
    if start < end:
        return start <= cur < end
    return cur >= start or cur < end         # 跨零点


def normalize_quiet(raw) -> str:
    """校验并规范化成 HH:MM-HH:MM；'不静默' 存空串。"""
    s = str(raw or "").strip().replace("—", "-").replace("~", "-")
    s = s.replace("：", ":")
    if not s or s in ("-", "无", "不静默", "off", "none"):
        return ""
    rng = parse_quiet(s)
    if rng is None:
        raise ValueError("静默时段格式要写成 23:00-07:00")
    return f"{rng[0] // 60:02d}:{rng[0] % 60:02d}-{rng[1] // 60:02d}:{rng[1] % 60:02d}"


# --------------------------------------------------------------------------
# 去重：同事件 + 同主体 在窗口内只发一次（防设备抖动刷屏）
# --------------------------------------------------------------------------
_dedupe: dict[tuple, float] = {}
_dedupe_lock = threading.Lock()


def dedupe_window(cfg) -> int:
    try:
        n = int(getattr(cfg, "notify_dedupe", 300) or 0)
    except (TypeError, ValueError):
        return 300
    return max(0, min(86400, n))


def _should_skip(code: str, subject: str, window: int) -> bool:
    if window <= 0:
        return False
    key = (code, subject or "")
    now = time.time()
    with _dedupe_lock:
        # 顺手清掉过期项，字典不会无限长
        for k in [k for k, t in _dedupe.items() if now - t > window]:
            _dedupe.pop(k, None)
        last = _dedupe.get(key)
        if last is not None and now - last < window:
            return True
        _dedupe[key] = now
    return False


def reset_dedupe() -> None:
    with _dedupe_lock:
        _dedupe.clear()


# --------------------------------------------------------------------------
# 推送历史：/data/notify.jsonl
# --------------------------------------------------------------------------
_lock = threading.Lock()


def history_path(state_file: str) -> str:
    d = os.path.dirname(os.path.abspath(state_file or "/data/state.json"))
    return os.path.join(d, "notify.jsonl")


def history_max(cfg) -> int:
    try:
        n = int(getattr(cfg, "notify_history_max", HISTORY_DEFAULT)
                or HISTORY_DEFAULT)
    except (TypeError, ValueError):
        n = HISTORY_DEFAULT
    return max(10, min(HISTORY_MAX_LIMIT, n))


def record_history(cfg, entry: dict) -> None:
    """追加一条投递记录并裁剪。任何文件故障都只记日志、不抛出。"""
    path = history_path(getattr(cfg, "state_file", "/data/state.json"))
    row = dict(entry)
    row.setdefault("ts", time.strftime("%Y-%m-%d %H:%M:%S"))
    try:
        with _lock:
            d = os.path.dirname(path)
            if d:
                os.makedirs(d, exist_ok=True)
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
            _trim(path, history_max(cfg))
    except OSError as e:
        log.warning("推送历史写不进去（不影响推送）：%s", e)


def read_history(cfg) -> list[dict]:
    """按时间正序返回（前端自己倒序展示）。坏行跳过。"""
    path = history_path(getattr(cfg, "state_file", "/data/state.json"))
    try:
        with open(path, encoding="utf-8") as f:
            lines = f.readlines()
    except OSError:
        return []
    out = []
    for ln in lines:
        ln = ln.strip()
        if not ln:
            continue
        try:
            v = json.loads(ln)
        except ValueError:
            continue
        if isinstance(v, dict):
            out.append(v)
    return out


def clear_history(cfg) -> None:
    path = history_path(getattr(cfg, "state_file", "/data/state.json"))
    try:
        with _lock:
            open(path, "w", encoding="utf-8").close()
    except OSError as e:
        log.warning("清空推送历史失败：%s", e)
    log.info("推送历史已清空：%s", path)


def _trim(path: str, maxn: int) -> None:
    if maxn <= 0:
        return
    with open(path, encoding="utf-8") as f:
        lines = f.readlines()
    if len(lines) <= maxn:
        return
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.writelines(lines[-maxn:])
    os.replace(tmp, path)


# --------------------------------------------------------------------------
# 投递入口
# --------------------------------------------------------------------------

def dispatch(cfg, code: str, text: str, subject: str = "",
             title: str | None = None, force: bool = False) -> list[dict]:
    """按事件推送一条通知（唯一入口，同步循环 / 计划任务 / 设备轮询都走它）。

    force=True 时忽略「总开关 / 事件订阅 / 静默时段 / 去重」（测试消息用）。
    返回各渠道的投递结果；没发出去返回空列表。**永不抛异常**。
    """
    try:
        return _dispatch(cfg, code, text, subject, title, force)
    except Exception as e:  # noqa: BLE001
        log.warning("通知派发失败（%s）：%s", code, e)
        return []


def _dispatch(cfg, code, text, subject, title, force) -> list[dict]:
    if not getattr(cfg, "notify_enabled", True) and not force:
        return []
    if not force and not event_enabled(cfg, code):
        return []
    level = level_of(code)
    if not force and level != LEVEL_URGENT \
            and in_quiet(getattr(cfg, "notify_quiet", "")):
        log.debug("静默时段内，跳过通知：%s", code)
        return []
    if not force and _should_skip(code, subject, dedupe_window(cfg)):
        log.debug("去重窗口内，跳过通知：%s / %s", code, subject)
        return []

    head = (icon_of(code) + " " + (title or title_of(code))).strip()
    ctx = {
        "title": head,
        "text": text or head,
        "level": level,
        "event": code,
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "panel": f"http://{getattr(cfg, 'host', '')}:"
                 f"{getattr(cfg, 'web_port', 6600)}",
    }
    results = notify.send_all(cfg, ctx)
    for r in results:
        record_history(cfg, {
            "channel": r.get("name", ""),
            "type": r.get("type", ""),
            "title": head,
            "event": code,
            "level": level,
            "ok": bool(r.get("ok")),
            "error": r.get("error", ""),
            "text": ctx["text"],
        })
    return results
