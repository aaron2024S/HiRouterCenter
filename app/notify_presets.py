# -*- coding: utf-8 -*-
"""
通知渠道预设：**一个渠道 = 一条数据**。

改造原则（照搬 dockhelm 的结论）：加一种渠道只加一条数据，不改投递代码。
一条预设 = 字段定义（前端据此渲染表单）+ URL 模板 + 请求头 + 请求体 + 响应校验。

三个必须踩对的坑：
  1. **JSON 体里的变量必须先转义** —— 正文里的换行 / 引号 / 反斜杠不转义就是非法 JSON，对方直接 400。
     这里的做法是「请求体写成 Python 结构，代入原始值后再 json.dumps」，
     让 json 自己负责转义，从根上不会漏。
  2. **URL 里的变量要 percent 编码，但 `server` / `url` 除外** ——
     整串 `https://` 被编码成 `https%3A%2F%2F` 就连协议头都解析不出来。
  3. **钉钉加签 / 飞书签名**是纯模板表达不了的，渲染前算好注入变量
     （标准库 hmac / hashlib / base64 就够，不装依赖）。

只依赖标准库：容器里没有第三方包，SMTP 用 smtplib，其余用 urllib。
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import smtplib
import ssl
import time
import urllib.parse
from email.message import EmailMessage
from email.utils import formataddr, formatdate

log = logging.getLogger("ipv6sync.notify")

TIMEOUT = 10

# URL 里**不做** percent 编码的变量：它们本身是完整地址
NO_QUOTE = frozenset({"server", "url"})
# _tail 是「已经自己编码好的查询串片段」，再编码一次就废了

LEVEL_URGENT = "urgent"

# 文本正文上限（企业微信 text 消息 2048 字节、Server 酱 32KB…按最严的来）
TEXT_LIMIT = 2000


# --------------------------------------------------------------------------
# 预设表
# --------------------------------------------------------------------------
# 字段定义里 l=标签 k=键 p=必填 ph=占位符 hp=下方提示 ty=控件类型 half=半宽并排
# body 可以是 dict（走 JSON）或 str（走纯文本/表单），字符串里的 {变量} 会被替换

PRESETS: dict[str, dict] = {
    "wecom": {
        "label": "企业微信机器人",
        "desc": "企业微信群机器人 Webhook，家庭群、部门群都能用。",
        "fields": [
            {"k": "key", "l": "Webhook Key", "p": 1,
             "ph": "群机器人 URL 里 key= 后面的部分",
             "hp": "群设置 → 群机器人 → 添加 → 复制 Webhook 地址，取 key= 后面那段"},
            {"k": "mentioned", "l": "@成员手机号", "ph": "13800138000，多人用逗号分隔"},
        ],
        "url": "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key={key}",
        "ct": "json",
        "body": {"msgtype": "text", "text": {"content": "{content}"}},
        "check": "errcode",
    },
    "telegram": {
        "label": "Telegram",
        "desc": "Telegram 机器人。需要这台机器能访问 api.telegram.org。",
        "fields": [
            {"k": "token", "l": "Bot Token", "p": 1, "ph": "123456:ABC-DEF…",
             "hp": "找 @BotFather 创建机器人后获得"},
            {"k": "chatId", "l": "Chat ID", "p": 1, "ph": "-1001234567890",
             "hp": "给机器人发条消息，再访问 /getUpdates 就能看到"},
        ],
        "url": "https://api.telegram.org/bot{token}/sendMessage",
        "noquote": ("token",),
        "ct": "json",
        "body": {"chat_id": "{chatId}", "text": "{content}",
                 "disable_web_page_preview": True},
        "check": "ok",
    },
    "bark": {
        "label": "Bark",
        "desc": "iOS 推送，可自建服务器。",
        "fields": [
            {"k": "server", "l": "服务器", "ph": "https://api.day.app",
             "hp": "自建 Bark 填自己的域名，留空用官方"},
            {"k": "key", "l": "Key", "p": 1, "ph": "打开 Bark App 首页就能看到"},
            {"k": "group", "l": "分组", "ph": "HiRouterCenter"},
        ],
        "url": "{server}/{key}",
        "ct": "json",
        "body": {"title": "{title}", "body": "{text}", "group": "{group}"},
        "check": "",
    },
    "ntfy": {
        "label": "ntfy",
        "desc": "开源推送，手机装 ntfy App 订阅同一个 Topic 即可，也支持自建。",
        "fields": [
            {"k": "server", "l": "服务器", "ph": "https://ntfy.sh"},
            {"k": "topic", "l": "主题 Topic", "p": 1, "ph": "hirouter-alerts",
             "hp": "这个 Topic 相当于暗号，别用太常见的名字"},
            {"k": "token", "l": "访问令牌", "ph": "自建且开了鉴权时填写"},
        ],
        "url": "{server}/{topic}",
        "ct": "text",
        "body": "{content}",
        "check": "",
    },
    "gotify": {
        "label": "Gotify",
        "desc": "自建 Gotify 推送（需要一个能公网或局域网访问的 Gotify 服务）。",
        "fields": [
            {"k": "server", "l": "服务器", "p": 1, "ph": "https://push.example.com"},
            {"k": "token", "l": "应用令牌", "p": 1,
             "hp": "Gotify「Apps」页创建的 App Token，不是 Client Token"},
        ],
        "url": "{server}/message?token={token}",
        "ct": "json",
        "body": {"title": "{title}", "message": "{text}", "priority": 5},
        "check": "error",
    },
    "dingtalk": {
        "label": "钉钉机器人",
        "desc": "钉钉群自定义机器人。",
        "fields": [
            {"k": "token", "l": "access_token", "p": 1,
             "ph": "机器人 Webhook 里的 access_token"},
            {"k": "secret", "l": "加签密钥",
             "hp": "安全设置选了「加签」才需要填"},
        ],
        # 加签参数拼在 {_tail} 里：没填密钥时它是空串，URL 干净
        "url": ("https://oapi.dingtalk.com/robot/send?access_token={token}"
                "{_tail}"),
        "noquote": ("_tail",),
        "ct": "json",
        "body": {"msgtype": "text", "text": {"content": "{content}"}},
        "check": "errcode",
        "sign": "dingtalk",
    },
    "feishu": {
        "label": "飞书机器人",
        "desc": "飞书群自定义机器人。",
        "fields": [
            {"k": "token", "l": "Webhook Token", "p": 1, "ph": "…/hook/ 后面的部分"},
            {"k": "secret", "l": "签名校验密钥",
             "hp": "开启了签名校验才需要填"},
        ],
        "url": "https://open.feishu.cn/open-apis/bot/v2/hook/{token}",
        "ct": "json",
        "body": {"msg_type": "text", "content": {"text": "{content}"}},
        "check": "code",
        "sign": "feishu",
    },
    "serverchan": {
        "label": "Server 酱",
        "desc": "方糖 Server 酱，推送到微信服务号。",
        "fields": [
            {"k": "sendkey", "l": "SendKey", "p": 1, "ph": "SCT…"},
        ],
        "url": "https://sctapi.ftqq.com/{sendkey}.send",
        "ct": "form",
        "body": {"title": "{title}", "desp": "{text}"},
        "check": "code",
    },
    "pushplus": {
        "label": "PushPlus",
        "desc": "PushPlus 微信推送。",
        "fields": [
            {"k": "token", "l": "Token", "p": 1},
            {"k": "topic", "l": "群组编码", "hp": "一对多推送时才需要填"},
        ],
        "url": "https://www.pushplus.plus/send",
        "ct": "json",
        "body": {"token": "{token}", "title": "{title}", "content": "{text}",
                 "template": "txt"},
        "check": "code",
    },
    "smtp": {
        "label": "邮件 SMTP",
        "desc": "发到邮箱。QQ / 163 这里要填「授权码」，不是登录密码。",
        "fields": [
            {"k": "host", "l": "SMTP 服务器", "p": 1, "ph": "smtp.qq.com"},
            {"k": "port", "l": "端口", "p": 1, "ph": "465（SSL）或 587（STARTTLS）",
             "half": 1},
            {"k": "username", "l": "用户名", "p": 1, "ph": "you@qq.com"},
            {"k": "password", "l": "密码 / 授权码", "p": 1, "ty": "password"},
            {"k": "from", "l": "发件人", "ph": "留空则用用户名"},
            {"k": "to", "l": "收件人", "p": 1, "ph": "多人用逗号分隔"},
        ],
        "url": "",
        "ct": "smtp",
        "body": "",
        "check": "",
    },
    "webhook": {
        "label": "自定义 Webhook",
        "desc": "任意 URL + 自定义请求头与请求体，接自建服务、自动化平台都行。",
        "fields": [
            {"k": "url", "l": "请求 URL", "p": 1, "ph": "https://example.com/hook"},
            {"k": "method", "l": "方法", "ph": "POST / PUT", "half": 1},
            {"k": "contentType", "l": "Content-Type", "ph": "application/json",
             "half": 1},
            {"k": "headers", "l": "自定义请求头", "ty": "area",
             "ph": '{"Authorization":"Bearer xxx"}',
             "hp": "JSON 对象，值里同样能写模板变量"},
            {"k": "body", "l": "请求体模板", "ty": "area",
             "ph": '{"title":"{{title}}","text":"{{text}}"}',
             "hp": "变量：{{title}} 标题 · {{text}} 正文 · {{level}} urgent/normal · "
                   "{{event}} 事件代码 · {{time}} 时间 · {{panel}} 面板地址"},
        ],
        "url": "{url}",
        "ct": "custom",
        "body": "",
        "check": "",
    },
}

# 用户可见的渠道顺序
CHANNEL_ORDER = ("wecom", "telegram", "bark", "ntfy", "gotify",
                 "dingtalk", "feishu", "serverchan", "pushplus",
                 "smtp", "webhook")

CHANNEL_NAME = {k: PRESETS[k]["label"] for k in CHANNEL_ORDER}


def specs() -> list[dict]:
    """给前端渲染表单用：只留字段定义、说明、标签，不含投递实现。"""
    out = []
    for t in CHANNEL_ORDER:
        p = PRESETS[t]
        out.append({
            "t": t,
            "l": p["label"],
            "d": p["desc"],
            "f": [dict(f) for f in p["fields"]],
        })
    return out


# --------------------------------------------------------------------------
# 模板渲染
# --------------------------------------------------------------------------

def _subst(value, ctx: dict, quote: bool = False):
    """把字符串里的 {var} 换成 ctx 里的值；quote=True 时做 percent 编码。

    只替换认识的变量，认不出的原样留着（避免把用户正文里的花括号吃掉）。
    故意不用 str.format —— 用户正文里出现 `{}` 会直接抛异常。
    """
    if not isinstance(value, str):
        return value
    out = []
    i = 0
    n = len(value)
    while i < n:
        if value[i] == "{":
            j = value.find("}", i + 1)
            if j < 0:
                out.append(value[i:])
                break
            key = value[i + 1:j]
            if key in ctx:
                raw = "" if ctx[key] is None else str(ctx[key])
                out.append(urllib.parse.quote(raw, safe="") if quote else raw)
                i = j + 1
                continue
        out.append(value[i])
        i += 1
    return "".join(out)


def _subst_deep(obj, ctx: dict):
    """递归替换 dict / list / str 里的变量（请求体走这条）。"""
    if isinstance(obj, dict):
        return {k: _subst_deep(v, ctx) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_subst_deep(v, ctx) for v in obj]
    return _subst(obj, ctx)


def _sign_vars(scheme: str, cfg: dict, ts: int) -> dict:
    """钉钉 / 飞书的加签变量。secret 为空就不签（对方没开加签时是对的）。"""
    secret = str(cfg.get("secret") or "").strip()
    if not secret:
        return {"_ts": str(ts), "_sign": "", "_tail": ""}
    if scheme == "dingtalk":
        # sign = urlencode(base64(HMAC-SHA256(key=secret, msg=timestamp+"\n"+secret)))
        # 这里给**原始 base64**，由 _quote_url_vars 统一做一次 percent 编码；
        # 提前 quote 一次会被二次编码（sign=xxx%253D）导致签名永远对不上。
        key = secret.encode("utf-8")
        msg = f"{ts}\n{secret}".encode("utf-8")
        digest = hmac.new(key, msg, hashlib.sha256).digest()
        sign = base64.b64encode(digest).decode("ascii")
        # 自己编码一次（urlencode 语义），再让 _quote_url_vars 原样放过
        tail = ("&timestamp=" + urllib.parse.quote_plus(str(ts))
                + "&sign=" + urllib.parse.quote_plus(sign))
        return {"_ts": str(ts), "_sign": sign, "_tail": tail}
    # 飞书：string_to_sign = timestamp + "\n" + secret，用它当 key，内容为空
    key = f"{ts}\n{secret}".encode("utf-8")
    digest = hmac.new(key, b"", hashlib.sha256).digest()
    return {"_ts": str(ts), "_sign": base64.b64encode(digest).decode("ascii"),
            "_tail": ""}


def _clip(text: str, limit: int = TEXT_LIMIT) -> str:
    """按字节截断（企业微信 2048 字节上限），不切坏多字节字符。"""
    b = text.encode("utf-8")
    if len(b) <= limit:
        return text
    return b[:limit].decode("utf-8", "ignore")


def missing_fields(ch_type: str, cfg: dict) -> list[str]:
    """返回没填的必填项标签，给界面提示和发送前校验共用。"""
    spec = PRESETS.get(ch_type)
    if not spec:
        return ["未知渠道类型"]
    out = []
    for f in spec["fields"]:
        if f.get("p") and not str(cfg.get(f["k"]) or "").strip():
            out.append(f["l"])
    return out


def normalize(ch_type: str, cfg: dict) -> dict:
    """清洗配置：去空白、补默认值、把 null 变成空串。"""
    clean = {}
    for f in PRESETS.get(ch_type, {}).get("fields", []):
        v = cfg.get(f["k"])
        clean[f["k"]] = "" if v is None else str(v).strip()
    # 端点默认值（留空就用官方）
    if ch_type == "bark" and not clean.get("server"):
        clean["server"] = "https://api.day.app"
    if ch_type == "ntfy" and not clean.get("server"):
        clean["server"] = "https://ntfy.sh"
    if ch_type == "gotify":
        clean["server"] = clean.get("server", "").rstrip("/")
    if ch_type in ("bark", "ntfy"):
        clean["server"] = clean.get("server", "").rstrip("/")
    if ch_type == "wecom":
        # 用户可能粘贴整条 webhook，这里只取 key= 后面那段
        key = clean.get("key", "")
        if "key=" in key:
            key = key.split("key=", 1)[1]
        clean["key"] = key.strip().strip("/")
    if ch_type == "feishu":
        tok = clean.get("token", "")
        if "/hook/" in tok:
            tok = tok.split("/hook/", 1)[1]
        clean["token"] = tok.strip().strip("/")
    if ch_type == "smtp" and not clean.get("from"):
        clean["from"] = clean.get("username", "")
    return clean


def build_request(ch_type: str, cfg: dict, ctx: dict, ts: int | None = None
                  ) -> dict:
    """把「渠道配置 + 事件变量」渲染成一次 HTTP 请求。

    返回 {"url","method","headers","data"}，data 是 bytes（无正文时为 b""）。
    缺必填项抛 ValueError（文案直接给用户看）。
    """
    spec = PRESETS.get(ch_type)
    if not spec:
        raise ValueError(f"不支持的渠道类型：{ch_type}")
    cfg = normalize(ch_type, cfg)
    miss = missing_fields(ch_type, cfg)
    if miss:
        raise ValueError("还没填：" + "、".join(miss))

    ts = int(ts if ts is not None else time.time())
    full = dict(ctx)
    full.update(cfg)
    # 公共派生变量
    full.setdefault("content", (str(ctx.get("title") or "") + "\n"
                                + str(ctx.get("text") or "")).strip())
    if spec.get("sign"):
        full.update(_sign_vars(spec["sign"], cfg, ts))

    # URL 里的变量逐个编码：server / url 这类整串地址不编码
    noquote = NO_QUOTE | frozenset(spec.get("noquote") or ())
    url = _quote_url_vars(spec["url"], full, noquote)

    headers = {"Content-Type": "application/json; charset=utf-8"}
    method = "POST"

    if ch_type == "webhook":
        headers = {}
        method = (cfg.get("method") or "POST").strip().upper()
        ctype = (cfg.get("contentType") or "").strip()
        if ctype:
            headers["Content-Type"] = ctype
        # 自定义模板统一用 {{var}}（和界面提示一致），先归一成 {var} 再替换
        raw_headers = (cfg.get("headers") or "").strip()
        if raw_headers:
            try:
                extra = json.loads(raw_headers)
            except Exception:  # noqa: BLE001
                raise ValueError("自定义请求头不是合法的 JSON") from None
            if isinstance(extra, dict):
                for k, v in extra.items():
                    hv = str(v).replace("{{", "{").replace("}}", "}")
                    headers[str(k)] = _subst(hv, full)
        tpl = (cfg.get("body") or "").replace("{{", "{").replace("}}", "}")
        text = _subst(tpl, full)
        data = text.encode("utf-8") if text else b""
        return {"url": url, "method": method, "headers": headers, "data": data}

    ct = spec["ct"]
    if ct == "json":
        payload = _subst_deep(spec["body"], full)
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    elif ct == "form":
        payload = _subst_deep(spec["body"], full)
        data = urllib.parse.urlencode(payload).encode("utf-8")
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
    elif ct == "smtp":
        data = b""
    else:  # 纯文本（ntfy）
        body = _subst(spec["body"], full)
        data = body.encode("utf-8")
        headers = {"Content-Type": "text/plain; charset=utf-8"}
        tok = cfg.get("token") or ""
        if tok:
            headers["Authorization"] = "Bearer " + tok
        if full.get("level") == LEVEL_URGENT:
            headers["Priority"] = "high"
            headers["Tags"] = "warning"

    # 企业微信 @人
    if ch_type == "wecom":
        payload = json.loads(data.decode("utf-8"))
        mobiles = [x.strip() for x in (cfg.get("mentioned") or "").split(",")
                   if x.strip()]
        if mobiles:
            payload["text"]["mentioned_mobile_list"] = mobiles
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    # 飞书签名要带 timestamp 字段（放在 body 里而不是 URL）
    if ch_type == "feishu" and cfg.get("secret"):
        payload = json.loads(data.decode("utf-8"))
        payload["timestamp"] = str(full.get("_ts", ""))
        payload["sign"] = str(full.get("_sign", ""))
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    return {"url": url, "method": method, "headers": headers, "data": data}


def _quote_url_vars(tpl: str, ctx: dict, noquote=NO_QUOTE) -> str:
    """渲染 URL：变量做 percent 编码，但 server / url 这类整串地址不编码。"""
    out = []
    i = 0
    n = len(tpl)
    while i < n:
        if tpl[i] == "{":
            j = tpl.find("}", i + 1)
            if j < 0:
                out.append(tpl[i:])
                break
            key = tpl[i + 1:j]
            if key in ctx:
                raw = "" if ctx[key] is None else str(ctx[key])
                out.append(raw if key in noquote
                           else urllib.parse.quote(raw, safe=""))
                i = j + 1
                continue
        out.append(tpl[i])
        i += 1
    return "".join(out)


# --------------------------------------------------------------------------
# 响应校验：HTTP 200 不等于成功（不少国产机器人恒回 200）
# --------------------------------------------------------------------------

def check_response(ch_type: str, body: str) -> str:
    """返回错误说明；空串表示成功。"""
    spec = PRESETS.get(ch_type, {})
    key = spec.get("check") or ""
    if not key:
        return ""
    try:
        j = json.loads(body) if body.strip() else None
    except Exception:  # noqa: BLE001
        return ""
    if not isinstance(j, dict):
        return ""
    if ch_type == "telegram":
        if j.get("ok") is False:
            return "Telegram：" + str(j.get("description") or "发送失败")
        return ""
    if ch_type == "feishu":
        return "" if j.get("code") in (0, None) else \
            f"飞书错误 {j.get('code')}: {j.get('msg', '')}"
    if ch_type == "serverchan":
        return "" if j.get("code") in (0, None) else \
            f"Server 酱错误 {j.get('code')}: {j.get('message', '')}"
    if ch_type == "pushplus":
        return "" if j.get("code") in (200, None) else \
            f"PushPlus 错误 {j.get('code')}: {j.get('msg', '')}"
    if ch_type == "gotify":
        err = j.get("error")
        return f"Gotify：{err}" if err else ""
    # wecom / dingtalk：errcode
    code = j.get(key)
    if code in (0, None):
        return ""
    msg = j.get("errmsg") or j.get("message") or ""
    label = CHANNEL_NAME.get(ch_type, ch_type)
    return f"{label}错误 {code}: {msg}"


# --------------------------------------------------------------------------
# SMTP 投递（单独一条路，smtplib）
# --------------------------------------------------------------------------

def send_mail(cfg: dict, subject: str, text: str) -> str:
    """发一封纯文本邮件。返回错误说明，空串表示成功。"""
    cfg = normalize("smtp", cfg)
    miss = missing_fields("smtp", cfg)
    if miss:
        return "还没填：" + "、".join(miss)
    host = cfg["host"]
    try:
        port = int(cfg.get("port") or 465)
    except ValueError:
        return "端口必须是数字"
    to_list = [x.strip() for x in (cfg.get("to") or "").replace("；", ",")
               .replace(";", ",").split(",") if x.strip()]
    if not to_list:
        return "还没填：收件人"

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = formataddr(("HiRouterCenter",
                              cfg.get("from") or cfg.get("username") or ""))
    msg["To"] = ", ".join(to_list)
    msg["Date"] = formatdate(localtime=True)
    msg.set_content(text)

    ctx = ssl.create_default_context()
    try:
        if port == 465:
            with smtplib.SMTP_SSL(host, port, timeout=TIMEOUT, context=ctx) as s:
                s.login(cfg["username"], cfg["password"])
                s.send_message(msg)
        else:
            with smtplib.SMTP(host, port, timeout=TIMEOUT) as s:
                s.ehlo()
                try:
                    s.starttls(context=ctx)
                    s.ehlo()
                except smtplib.SMTPException:
                    pass          # 服务端不支持 STARTTLS 就明文发
                s.login(cfg["username"], cfg["password"])
                s.send_message(msg)
    except smtplib.SMTPAuthenticationError:
        return "邮箱登录被拒：账号或授权码不对"
    except smtplib.SMTPException as e:
        return f"邮件发送失败：{e}"
    except OSError as e:
        return f"连不上邮件服务器：{e}"
    return ""
