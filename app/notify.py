# -*- coding: utf-8 -*-
"""
通知投递：渠道列表 + 预设驱动。

**一个渠道 = 一条配置**：
    {"id": "c3f1a2", "type": "wecom", "name": "家庭群",
     "enabled": true, "config": {"key": "..."}}

加一种渠道只加 `notify_presets.PRESETS` 里的一条数据，这里不用改。
投递本身分两条路：SMTP 走 smtplib，其余走 urllib 发 HTTP。

设计约束：
  · 只依赖标准库 —— 容器里没有第三方依赖
  · send_all() **永不抛异常**：通知只是锦上添花，任何失败都只返回错误说明，
    绝不能影响同步主流程
"""
from __future__ import annotations

import json
import logging
import os
import secrets
import urllib.request

from . import notify_presets as P

log = logging.getLogger("ipv6sync.notify")

TIMEOUT = P.TIMEOUT

# 设置文件里渠道列表的键（和 settings.py 里的常量必须一致）
CHANNELS_KEY = "NOTIFY_CHANNELS"


# --------------------------------------------------------------------------
# 渠道列表的读写
# --------------------------------------------------------------------------

def _new_id() -> str:
    return secrets.token_hex(3)


def normalize_channel(raw: dict) -> dict:
    """校验并规范化一条渠道配置；不合法抛 ValueError（文案给用户看）。"""
    if not isinstance(raw, dict):
        raise ValueError("渠道配置必须是一个对象")
    ctype = str(raw.get("type") or "").strip()
    if ctype not in P.PRESETS:
        raise ValueError(f"不认识的渠道类型：{ctype or '（空）'}")
    name = str(raw.get("name") or "").strip() or P.CHANNEL_NAME[ctype]
    if len(name) > 32:
        raise ValueError(f"渠道名称「{name}」太长（最多 32 个字）")
    cfg = raw.get("config") or {}
    if not isinstance(cfg, dict):
        raise ValueError("渠道配置的 config 必须是对象")
    clean = P.normalize(ctype, cfg)
    # 只留填了值的键，不往设置文件里塞一堆空字符串
    clean = {k: v for k, v in clean.items() if str(v).strip()}
    return {
        "id": str(raw.get("id") or "").strip() or _new_id(),
        "type": ctype,
        "name": name,
        "enabled": bool(raw.get("enabled", True)),
        "config": clean,
    }


def _split_ntfy_url(url: str) -> tuple[str, str]:
    """老配置的 ntfy 地址可能自带主题：https://ntfy.sh/mytopic → (服务器, 主题)。"""
    import urllib.parse
    u = (url or "").strip().rstrip("/")
    if not u:
        return "", ""
    p = urllib.parse.urlparse(u)
    topic = p.path.strip("/")
    if not p.scheme:
        return u, ""
    base = f"{p.scheme}://{p.netloc}"
    return base, topic


def migrate_legacy(cfg) -> list[dict]:
    """把老的「三个开关 + 三段固定配置」转成渠道列表（只转已启用的+填了的）。"""
    out: list[dict] = []

    ntfy_url = getattr(cfg, "notify_ntfy_url", "") or ""
    ntfy_tok = getattr(cfg, "notify_ntfy_token", "") or ""
    if getattr(cfg, "notify_ntfy_enabled", False) or ntfy_url:
        server, topic = _split_ntfy_url(ntfy_url)
        out.append(normalize_channel({
            "type": "ntfy", "name": "ntfy",
            "enabled": bool(getattr(cfg, "notify_ntfy_enabled", False)),
            "config": {"server": server, "topic": topic or "ipv6sync",
                       "token": ntfy_tok},
        }))

    gotify_url = getattr(cfg, "notify_gotify_url", "") or ""
    gotify_tok = getattr(cfg, "notify_gotify_token", "") or ""
    if getattr(cfg, "notify_gotify_enabled", False) or gotify_url:
        out.append(normalize_channel({
            "type": "gotify", "name": "gotify",
            "enabled": bool(getattr(cfg, "notify_gotify_enabled", False)),
            "config": {"server": gotify_url, "token": gotify_tok},
        }))

    wecom_id = getattr(cfg, "notify_wecom_id", "") or ""
    if getattr(cfg, "notify_wecom_enabled", False) or wecom_id:
        out.append(normalize_channel({
            "type": "wecom", "name": "企业微信",
            "enabled": bool(getattr(cfg, "notify_wecom_enabled", False)),
            "config": {"key": wecom_id},
        }))
    return out


def channels(cfg) -> list[dict]:
    """当前所有渠道（含未启用的）。新格式优先，没有就用老配置临时转一份。

    这里**不落盘**：老用户什么都不改也能照常用；一旦在任何地方保存过渠道，
    新格式就写进设置文件，之后以新格式为准。
    """
    raw = getattr(cfg, "notify_channels", None)
    if raw:
        out = []
        for it in raw:
            try:
                out.append(normalize_channel(it))
            except ValueError as e:
                log.warning("忽略一条不合法的通知渠道：%s", e)
        if out:
            return out
    return migrate_legacy(cfg)


def is_configured(cfg) -> bool:
    """有没有至少一个启用且填全了的渠道。"""
    for c in channels(cfg):
        if c["enabled"] and not P.missing_fields(c["type"], c["config"]):
            return True
    return False


def save(cfg, items: list) -> list[dict]:
    """校验整份渠道列表并写回 cfg（落盘由设置层负责）。"""
    if not isinstance(items, list):
        raise ValueError("渠道列表必须是一个数组")
    out: list[dict] = []
    seen_id: set = set()
    for it in items:
        c = normalize_channel(it)
        if c["id"] in seen_id:
            c["id"] = _new_id()
        seen_id.add(c["id"])
        out.append(c)
    cfg.notify_channels = out
    return out


# --------------------------------------------------------------------------
# 投递
# --------------------------------------------------------------------------

def _post(url: str, data: bytes, headers: dict, method: str = "POST"
          ) -> tuple[bool, str]:
    """发一次 HTTP，返回 (HTTP 层是否成功, 响应正文)。"""
    req = urllib.request.Request(url, data=data or None, headers=headers or {},
                                 method=method or "POST")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            body = r.read().decode("utf-8", "replace")
            return (200 <= r.status < 300), body
    except Exception as e:  # noqa: BLE001
        body = ""
        resp = getattr(e, "read", None)
        if callable(resp):
            try:
                body = resp().decode("utf-8", "replace")
            except Exception:  # noqa: BLE001
                body = ""
        return False, body or "连不上或请求被拒"


def deliver(channel: dict, ctx: dict) -> tuple[bool, str]:
    """按一条渠道配置投递一次。返回 (是否成功, 错误说明)。"""
    ctype = channel["type"]
    cfg = channel.get("config") or {}
    if ctype == "smtp":
        err = P.send_mail(cfg, ctx.get("title", ""), ctx.get("text", ""))
        return (not err), err
    try:
        req = P.build_request(ctype, cfg, ctx)
    except ValueError as e:
        return False, str(e)
    ok, body = _post(req["url"], req["data"], req["headers"], req["method"])
    if not ok:
        # 尽量把对方的错误说明挖出来，比一句「HTTP 400」有用
        msg = P.check_response(ctype, body)
        return False, msg or (body[:180].strip() or "请求失败")
    err = P.check_response(ctype, body)
    if err:
        return False, err
    return True, ""


def send_all(cfg, ctx: dict) -> list[dict]:
    """向所有「启用且配置完整」的渠道各推一条。

    返回 [{"id","name","type","ok","error"}, ...]；配置不全的渠道跳过并说明原因，
    一个渠道失败不影响其它渠道。**永不抛异常**。
    """
    results: list[dict] = []
    for ch in channels(cfg):
        if not ch["enabled"]:
            continue
        miss = P.missing_fields(ch["type"], ch["config"])
        if miss:
            results.append({"id": ch["id"], "name": ch["name"],
                            "type": ch["type"], "ok": False,
                            "error": "配置不全：" + "、".join(miss)})
            continue
        try:
            ok, err = deliver(ch, ctx)
        except Exception as e:  # noqa: BLE001
            log.warning("通知发送失败（%s / %s）：%s", ch["name"], ch["type"], e)
            ok, err = False, f"{type(e).__name__}: {e}"
        if not ok:
            log.warning("通知发送失败（%s / %s）：%s", ch["name"], ch["type"], err)
        results.append({"id": ch["id"], "name": ch["name"],
                        "type": ch["type"], "ok": ok, "error": err})
    return results


def send_test(cfg, channel: dict) -> tuple[bool, str]:
    """给单条渠道发一条测试消息（不看总开关、不看事件订阅）。"""
    import time
    ctx = {
        "title": "测试通知",
        "text": "这是一条来自 HiRouterCenter 的测试消息。\n"
                "收到它说明这个渠道配好了。",
        "level": "normal",
        "event": "test",
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "panel": f"http://{getattr(cfg, 'host', '')}:{getattr(cfg, 'web_port', 6600)}",
    }
    try:
        return deliver(channel, ctx)
    except Exception as e:  # noqa: BLE001
        return False, f"{type(e).__name__}: {e}"
