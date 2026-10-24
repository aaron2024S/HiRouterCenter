# -*- coding: utf-8 -*-
"""路由器自身的信息（首页那张信息卡用）。

字段来源分两类，**都做「取不到就返回空串」**，让前端整格隐藏，绝不显示假数据：

  · `system/deviceinfo` —— 免登录就能读。型号在 `FriendlyName`（真机实测：
    「华为凌霄子母路由 Q7 网线版」），运行时长 `UpTime` 是秒；`SoftwareVersion`
    在这台固件上直接返回 "-"，所以固件版本要按「不是 - 才显示」来判。
  · `ntwk/wan` / `ntwk/ipv6_wan` 等 —— 需登录。

为什么 WAN IPv6 不能「按形状捞第一个全球单播」：`ipv6_wan` 返回体里
**DNS 服务器（240e:5a::6666）和前缀（240e:xxx::/64）也是全球单播**，
捞到哪个全看字段顺序 —— 表现就是「一会正常一会变成 DNS/前缀」。
所以 v6 取地址必须两段式：

  1. **键名优先**：键名里同时出现「wan/ip/v6 语义」，值是完整地址才认；
  2. **形状兜底**：只认**不含 `::` 的完整 8 段地址** —— WAN 口地址永远是
     完整形式，而前缀（…::/64）和 DNS（…::6666）几乎都是压缩形式。

Wi-Fi 同理：不再深度扫任意字符串（会把设备名、时间串捞进来），只认
**键名带 ssid** 的值；信道只认键名带 channel（排除 deploy/mode）的整数，
再按数值范围归频段（1-14 → 2.4G，36-196 → 5G），不赌字段名。
"""
from __future__ import annotations

import ipaddress
import logging
import re

log = logging.getLogger("ipv6sync.router_info")

# 型号的候选字段，按可信度排（FriendlyName 是给用户看的中文型号名）
_PRODUCT_KEYS = ("FriendlyName", "ProductName", "DeviceName")
_MODEL_KEYS = ("NetECCode", "DeviceModel", "Model", "HardwareVersion")

_MAC_RE = re.compile(r"^([0-9a-f]{2}[:-]){5}[0-9a-f]{2}$", re.I)

# Wi-Fi / 信道探测的接口清单。不同固件暴露的字段不一样，多试几个；
# channelinfo / wlanradio 即便没有 SSID，也可能带当前信道。
_WIFI_PATHS = ("wlan", "wlanhost", "wlanadv", "hostssid",
               "channelinfo", "wlanradio")


# --------------------------------------------------------------------------
# 通用小工具
# --------------------------------------------------------------------------

def _walk(obj, depth: int = 0):
    """深度遍历，产出 (键名, 值)。列表没有键名，只继续往下走。"""
    if depth > 8:
        return
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k, v
            yield from _walk(v, depth + 1)
    elif isinstance(obj, list):
        for v in obj:
            yield from _walk(v, depth + 1)


def _is_num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _first(body, pred):
    """返回第一个满足 pred(键名小写, 值) 的值；没有就 None。"""
    if not isinstance(body, (dict, list)):
        return None
    for k, v in _walk(body):
        try:
            if pred(str(k).lower(), v):
                return v
        except Exception:                        # noqa: BLE001 — 判定函数随便抛
            continue
    return None


def _scan_strings(obj, depth: int = 0, out: list | None = None) -> list[str]:
    """深度收集所有非空字符串值（键名不参与判断）。"""
    if out is None:
        out = []
    if depth > 6:
        return out
    if isinstance(obj, dict):
        for v in obj.values():
            if isinstance(v, str):
                if v.strip():
                    out.append(v.strip())
            else:
                _scan_strings(v, depth + 1, out)
    elif isinstance(obj, list):
        for v in obj:
            if isinstance(v, str):
                if v.strip():
                    out.append(v.strip())
            else:
                _scan_strings(v, depth + 1, out)
    return out


# --------------------------------------------------------------------------
# 地址 / MAC / 版本
# --------------------------------------------------------------------------

def _public_ipv4(text: str) -> bool:
    try:
        a = ipaddress.IPv4Address(text)
    except ValueError:
        return False
    return not (a.is_private or a.is_loopback or a.is_link_local
                or a.is_multicast or a.is_unspecified)


def _lan_ipv4(text: str) -> bool:
    try:
        a = ipaddress.IPv4Address(text)
    except ValueError:
        return False
    return a.is_private


def _global_ipv6(text: str) -> bool:
    try:
        a = ipaddress.IPv6Address(text)
    except ValueError:
        return False
    if a.is_loopback or a.is_link_local or a.is_multicast or a.is_unspecified:
        return False
    # 只认 2000::/3（全球单播），跳开 fd00/fe80 这些
    return int(a) >> 125 == 0b001


def _pick_addr(body, kind: str) -> str:
    """从响应体里挑「WAN 地址」。键名优先，形状兜底；见模块头注释。"""
    if not isinstance(body, (dict, list)):
        return ""

    def by_key(k: str, v):
        if kind == "v6":
            if ("ipv6" in k or "v6" in k) and ("ip" in k or "addr" in k) \
                    and isinstance(v, str) and _global_ipv6(v.split("/")[0].strip()):
                return True
        else:
            if "ipv6" not in k and "v6" not in k and "dns" not in k \
                    and ("ip" in k or "addr" in k) and isinstance(v, str) \
                    and _public_ipv4(v.split("/")[0].strip()):
                return True
        return False

    v = _first(body, by_key)
    if isinstance(v, str):
        return v.split("/")[0].strip()

    for s in _scan_strings(body):
        core = s.split("/")[0].strip()
        if kind == "v4" and _public_ipv4(core):
            return core
        if kind == "v6" and _global_ipv6(core) and "::" not in core:
            return core
    return ""


def _pick_lan_ip4(body) -> str:
    """LAN IPv4（私网地址）：键名带 lan + ip/addr 优先，形状兜底。"""
    if not isinstance(body, (dict, list)):
        return ""

    def hit(k: str, v):
        return "lan" in k and ("ip" in k or "addr" in k) \
            and isinstance(v, str) and _lan_ipv4(v.split("/")[0].strip())

    v = _first(body, hit)
    if isinstance(v, str):
        return v.split("/")[0].strip()
    for s in _scan_strings(body):
        if _lan_ipv4(s.split("/")[0].strip()):
            return s.split("/")[0].strip()
    return ""


def _pick_mac(body, want: str) -> str:
    """按 MAC 形状找值；want 是 'wan' / 'lan'，先筛键名带对应词的。"""
    if not isinstance(body, (dict, list)):
        return ""
    vals = {want: [], "": []}
    for k, v in _walk(body):
        if isinstance(v, str) and _MAC_RE.match(v.strip()):
            k = k.lower()
            if want in k:
                vals[want].append(v.strip().upper())
            else:
                vals[""].append(v.strip().upper())
    pool = vals[want] or vals[""]
    return pool[0] if pool else ""


def _pick_string(body, needle: str, *, forbid: tuple = ()) -> str:
    """键名含 needle 的第一个非空字符串（可排除若干词）。"""
    def hit(k: str, v):
        return needle in k and not any(f in k for f in forbid) \
            and isinstance(v, str) and v.strip() not in ("", "-")
    v = _first(body, hit)
    return v.strip() if isinstance(v, str) else ""


def _uptime_text(sec) -> str:
    try:
        n = int(sec)
    except (TypeError, ValueError):
        return ""
    if n <= 0:
        return ""
    d, rest = divmod(n, 86400)
    h, rest = divmod(rest, 3600)
    m = rest // 60
    if d:
        return "%d 天 %d 小时" % (d, h)
    if h:
        return "%d 小时 %d 分" % (h, m)
    return "%d 分钟" % m


# --------------------------------------------------------------------------
# 各接口读取
# --------------------------------------------------------------------------

def _safe_get(router, path: str):
    try:
        return router.get(path)
    except Exception as e:                      # noqa: BLE001 — 信息卡不能拖垮整页
        log.debug("读 %s 失败：%s", path, e)
        return None


def _deviceinfo(router) -> dict:
    info = _safe_get(router, "deviceinfo")
    return info if isinstance(info, dict) else {}


def _wifi(router) -> tuple[dict, dict]:
    """返回 (SSID 按频段, 信道按频段)。

    SSID 只认键名带 ssid 的字符串，键名能分出 2.4G / 5G 就分；分不出来、
    或两个频段同名（**双频合一**，2.4G 和 5G 共用一个名称）就合并成一个键。
    信道按数值归频段：1-14 → 2.4G，36-196 → 5G；ChannelDeploy /
    NetChannelMode 这类「含 channel 但不是信道号」的键明确排除。
    """
    names: dict[str, list[str]] = {"2.4G": [], "5G": [], "": []}
    chans: dict[str, int] = {}
    for path in _WIFI_PATHS:
        body = _safe_get(router, path)
        if not isinstance(body, (dict, list)):
            continue
        for k, v in _walk(body):
            ks = str(k).lower()
            if isinstance(v, str) and "ssid" in ks:
                s = v.strip()
                if not 1 <= len(s) <= 32 or "." in s or ":" in s:
                    continue                    # 太长 / 像 IP，不是 SSID
                flat = ks.replace("_", "").replace("-", "").replace(".", "")
                if "5g" in flat:
                    names["5G"].append(s)
                elif "24" in flat or "2g" in flat:
                    names["2.4G"].append(s)
                else:
                    names[""].append(s)
            elif _is_num(v) and "channel" in ks \
                    and "deploy" not in ks and "mode" not in ks:
                n = int(v)
                if 1 <= n <= 14:
                    chans.setdefault("2.4G", n)
                elif (36 <= n <= 64) or (100 <= n <= 165):
                    chans.setdefault("5G", n)

    b24 = (names["2.4G"] or [None])[0]
    b5 = (names["5G"] or names[""] or [None])[0]
    if b24 and b5 and b24 == b5:
        ssid = {"双频合一": b24}                # 2.4G / 5G 同名
    elif b24 or b5:
        ssid = {}
        if b24:
            ssid["2.4G"] = b24
        if b5:
            ssid["5G"] = b5
    else:
        ssid = {}
    return ssid, chans


def collect(router) -> dict:
    """汇总首页信息卡要显示的一切。任何一项读不到就是空串 / 空字典。"""
    info = _deviceinfo(router)
    cust = info.get("custinfo") if isinstance(info.get("custinfo"), dict) else {}

    product = ""
    for k in _PRODUCT_KEYS:
        v = info.get(k) or cust.get("CustZHFriendlyName" if k == "FriendlyName" else "")
        if isinstance(v, str) and v.strip():
            product = v.strip()
            break

    model = ""
    for k in _MODEL_KEYS:
        v = info.get(k)
        if isinstance(v, str) and v.strip() and v.strip() != "-":
            model = v.strip()
            break

    software = ""
    v = info.get("SoftwareVersion")
    if isinstance(v, str) and v.strip() and v.strip() != "-":
        software = v.strip()

    # HarmonyOS 版本：键名带 harmony 的第一个字符串（各固件键名不稳，按词匹配）
    harmony = _pick_string(info, "harmony")

    out = {
        "product": product,
        "model": model,
        "hardware": str(info.get("HardwareVersion") or "").strip(),
        "serial": str(info.get("SerialNumber") or "").strip(),
        "firmware": software,
        "harmony": harmony,
        "uptime": _uptime_text(info.get("UpTime")),
        "wan4": "",
        "wan6": "",
        "lan_ip4": "",
        "prefix6": "",
        "wan_mac": _pick_mac(info, "wan"),
        "lan_mac": _pick_mac(info, "lan"),
        "ssid": {},
        "channels": {},
        "power_mode": None,      # 0 睡眠 / 1 一般 / 2 穿墙，读不到就是 None
    }

    # 功率模式（信息卡上「功率模式 <当前>」那个按钮要显示它）
    radio = _safe_get(router, "wlanradio")
    if isinstance(radio, dict) and radio.get("PowerMode") is not None:
        try:
            out["power_mode"] = int(radio["PowerMode"])
        except (TypeError, ValueError):
            pass

    # WAN 地址要登录；读不到就让那两格空着
    wan_body = _safe_get(router, "wan")
    if wan_body is not None:
        out["wan4"] = _pick_addr(wan_body, "v4")
        if not out["wan_mac"]:
            out["wan_mac"] = _pick_mac(wan_body, "wan")
    v6_body = _safe_get(router, "ipv6_wan")
    if v6_body is not None:
        out["wan6"] = _pick_addr(v6_body, "v6")
        if not out["prefix6"]:
            p = _pick_string(v6_body, "prefix")
            out["prefix6"] = p if ":" in p else ""
    lan6 = _safe_get(router, "ipv6_lan")
    if lan6 is not None:
        p = _pick_string(lan6, "prefix")
        if ":" in p:
            out["prefix6"] = out["prefix6"] or p
    if not out["lan_ip4"]:
        out["lan_ip4"] = _pick_lan_ip4(lan6 or {}) or _pick_lan_ip4(info)
    if not out["lan_ip4"]:
        out["lan_ip4"] = _pick_lan_ip4(_safe_get(router, "lan_host") or {})
    if not out["lan_mac"]:
        out["lan_mac"] = _pick_mac(lan6 or {}, "lan")

    try:
        out["ssid"], out["channels"] = _wifi(router)
    except Exception as e:                      # noqa: BLE001
        log.debug("读 Wi-Fi 信息失败：%s", e)

    return out
