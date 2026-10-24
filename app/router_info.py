# -*- coding: utf-8 -*-
"""路由器自身的信息（首页那张信息卡用）。

字段来源分两类，**都做「取不到就返回空串」**，让前端整格隐藏，绝不显示假数据：

  · `system/deviceinfo` —— 免登录就能读。型号在 `FriendlyName`（真机实测：
    「华为凌霄子母路由 Q7 网线版」），运行时长 `UpTime` 是秒；`SoftwareVersion`
    在这台固件上直接返回 "-"，所以固件版本要按「不是 - 才显示」来判。
  · `ntwk/wan` / `ntwk/ipv6_wan` —— 需登录。地址从返回体里**按形状捞**，
    不赌字段名（同 tasks.find_wan_id 的思路：固件版本之间字段名不稳定）。
"""
from __future__ import annotations

import ipaddress
import logging

log = logging.getLogger("ipv6sync.router_info")

# 型号的候选字段，按可信度排（FriendlyName 是给用户看的中文型号名）
_PRODUCT_KEYS = ("FriendlyName", "ProductName", "DeviceName")
_MODEL_KEYS = ("NetECCode", "DeviceModel", "Model", "HardwareVersion")


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


def _public_ipv4(text: str) -> bool:
    try:
        a = ipaddress.IPv4Address(text)
    except ValueError:
        return False
    return not (a.is_private or a.is_loopback or a.is_link_local
                or a.is_multicast or a.is_unspecified)


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
    """从任意响应体里挑一个最像「WAN 地址」的字符串。"""
    if not isinstance(body, (dict, list)):
        return ""
    for s in _scan_strings(body):
        # 去掉可能的掩码 / 前缀长度：1.2.3.4/24、2408::1/64
        core = s.split("/")[0].strip()
        if kind == "v4" and _public_ipv4(core):
            return core
        if kind == "v6" and _global_ipv6(core):
            return core
    return ""


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


def _deviceinfo(router) -> dict:
    try:
        info = router.get("deviceinfo")
    except Exception as e:                      # noqa: BLE001 — 信息卡不能拖垮整页
        log.debug("读设备信息失败：%s", e)
        return {}
    return info if isinstance(info, dict) else {}


def _ssid(router) -> dict:
    """Wi-Fi 名称。固件 `wlanradio` 不含 SSID，依次试几个接口，取到就用。

    取不到返回空字典 —— 首页那一格整格隐藏，不显示「—」占位。
    """
    for path in ("wlan", "hostssid", "wlanadv"):
        try:
            body = router.get(path)
        except Exception:                        # noqa: BLE001
            continue
        names: list[str] = []
        for s in _scan_strings(body):
            # SSID 通常带字母数字、长度 1~32、不含空格开头的地址样式
            if 1 <= len(s) <= 32 and "." not in s and ":" not in s \
                    and s not in names:
                names.append(s)
        if names:
            out = {}
            left = [n for n in names if "5g" not in n.lower()]
            five = [n for n in names if "5g" in n.lower()]
            if left:
                out["2.4G"] = left[0]
            if five:
                out["5G"] = five[0]
            elif len(left) > 1:
                out["5G"] = left[1]
            if out:
                return out
    return {}


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

    out = {
        "product": product,
        "model": model,
        "hardware": str(info.get("HardwareVersion") or "").strip(),
        "serial": str(info.get("SerialNumber") or "").strip(),
        "firmware": software,
        "uptime": _uptime_text(info.get("UpTime")),
        "wan4": "",
        "wan6": "",
        "ssid": {},
        "power_mode": None,      # 0 睡眠 / 1 一般 / 2 穿墙，读不到就是 None
    }

    # 功率模式（信息卡上「功率模式 <当前>」那个按钮要显示它）
    try:
        radio = router.get("wlanradio")
        if isinstance(radio, dict) and radio.get("PowerMode") is not None:
            out["power_mode"] = int(radio["PowerMode"])
    except Exception as e:                      # noqa: BLE001
        log.debug("读功率模式失败：%s", e)

    # WAN 地址要登录；读不到就让那两格空着
    for key, path, kind in (("wan4", "wan", "v4"), ("wan6", "ipv6_wan", "v6")):
        try:
            out[key] = _pick_addr(router.get(path), kind)
        except Exception as e:                  # noqa: BLE001
            log.debug("读 %s 失败：%s", path, e)

    try:
        out["ssid"] = _ssid(router)
    except Exception as e:                      # noqa: BLE001
        log.debug("读 Wi-Fi 名称失败：%s", e)

    return out
