# -*- coding: utf-8 -*-
"""网络唤醒（Wake-on-LAN）：把魔术包广播到局域网，唤起关机/休眠的设备。

为什么这个功能放在本程序里：容器以 `network_mode: host` 运行，宿主机的网卡
直接挂在家庭局域网上 —— 魔术包能真正落到设备的广播域里。换成 bridge 网络，
包只会发进容器自己的命名空间，什么都叫不醒。

**只负责「发出去」，不负责「确认成功」**：
设备从收到魔术包到出现在路由器设备列表里，中间隔着 BIOS 自检、网卡链路协商、
DHCP、Wi-Fi 关联，以及路由器 `HostInfo` 缓存自身的刷新节奏（它是邻居表，
不是实时状态机）。这几段时长我们都控制不了、也没有文档，任何固定 TTL 都会
误报「唤醒失败」—— 而误报的代价比不报大得多：设备明明在正常开机，用户却以为
坏了，回头去翻 BIOS。
"""
from __future__ import annotations

import ipaddress
import logging
import socket
import struct
import threading
import time

from . import discover

log = logging.getLogger("ipv6sync.wol")

PROC_NET_ROUTE = "/proc/net/route"
# 9 = discard、7 = echo。两个都是业界惯例端口，不同网卡认的不一样，都发。
WOL_PORTS = (9, 7)
ROUNDS = 3               # 重复几轮（个别网卡对单次广播不敏感）
ROUND_GAP = 0.15         # 轮间隔（秒）
BROADCAST_ALL = "255.255.255.255"


def magic_packet(mac: str) -> bytes:
    """WOL 魔术包：6 个 0xFF + 16 遍 MAC，共 102 字节。

    MAC 的写法（冒号、横杠、大小写、有无分隔符）全都不影响 —— 一律先过
    `discover.norm_mac` 归一成 12 个十六进制字符。
    """
    hexs = discover.norm_mac(mac)
    if len(hexs) != 12:
        raise ValueError(f"MAC 格式不对：{mac!r}")
    return b"\xff" * 6 + bytes.fromhex(hexs) * 16


def _hex_addr(text: str) -> int:
    """/proc/net/route 里的地址是 8 位十六进制的**小端** u32，要翻回来。"""
    return struct.unpack("<I", bytes.fromhex(text))[0]


def _routes() -> list[tuple[int, int]]:
    """读 /proc/net/route，返回 [(目标网段, 掩码)]，按掩码长度从长到短。

    只保留掩码非 0 的行 —— 默认路由（掩码 0）对算广播地址没用。
    读不到（非 Linux / 没挂 proc）就返回空表，调用方退回按 /24 猜。
    """
    rows: list[tuple[int, int]] = []
    try:
        with open(PROC_NET_ROUTE, encoding="utf-8") as f:
            for line in f.readlines()[1:]:
                parts = line.split()
                if len(parts) < 8:
                    continue
                try:
                    dest, mask = _hex_addr(parts[1]), _hex_addr(parts[7])
                except ValueError:
                    continue
                if not mask:
                    continue
                rows.append((dest & mask, mask))
    except OSError as e:
        log.debug("读 %s 失败：%s", PROC_NET_ROUTE, e)
    rows.sort(key=lambda r: bin(r[1]).count("1"), reverse=True)
    return rows


def broadcast_targets(ipv4: str = "", extra=()) -> list[str]:
    """算设备所在网段的定向广播地址。

    优先按路由表里**最具体**的那条算 —— /16、/20 这些非 /24 网段也能算对；
    路由表读不到或对不上（比如设备 IP 压根不在任何直连网段里）就退回 /24 猜
    一个，家用网段绝大多数就是 /24。

    另外始终带上 255.255.255.255：有的网卡只认真实广播、有的交换机只转定向
    广播，两个都发最省事（每个包 102 字节，代价可以忽略）。
    """
    out: list[str] = []
    try:
        ip = ipaddress.IPv4Address((ipv4 or "").strip())
    except ValueError:
        ip = None
    if ip is not None:
        for dest, mask in _routes():
            if int(ip) & mask == dest:
                out.append(str(ipaddress.IPv4Address(dest | (~mask & 0xFFFFFFFF))))
                break
        else:
            head = str(ip).split(".")[:3]
            out.append(".".join(head + ["255"]))
    out.append(BROADCAST_ALL)
    for item in extra or ():
        item = str(item or "").strip()
        if item:
            out.append(item)
    # 去重但保持顺序（路由算出来的定向广播可能恰好就是 255.255.255.255）
    res: list[str] = []
    for addr in out:
        if addr not in res:
            res.append(addr)
    return res


def send(mac: str, ipv4: str = "", extra=()) -> dict:
    """发魔术包。返回 {ok, mac, sent, targets} 或 {ok: False, error}。

    单个目标发失败不中断其余目标（某个网卡没权限、地址不可达都可能发生），
    只有**一个包都没发出去**才算整体失败。
    """
    try:
        pkt = magic_packet(mac)
    except ValueError as e:
        return {"ok": False, "mac": mac, "error": str(e)}

    targets = broadcast_targets(ipv4, extra)
    sent = 0
    errors: list[str] = []
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        for rnd in range(ROUNDS):
            for target in targets:
                for port in WOL_PORTS:
                    try:
                        sock.sendto(pkt, (target, port))
                        sent += 1
                    except OSError as e:
                        errors.append(f"{target}:{port} {e}")
            if rnd + 1 < ROUNDS:
                time.sleep(ROUND_GAP)
    finally:
        sock.close()

    if not sent:
        uniq = list(dict.fromkeys(errors))[:3]
        return {"ok": False, "mac": mac, "targets": targets,
                "error": "一个包都没能发出去：" + "; ".join(uniq)}
    return {"ok": True, "mac": mac, "sent": sent, "targets": targets}


class Throttle:
    """按 MAC 限频：同一台设备 cooldown 秒内只放行一次，另有全局配额。

    网页上连点、开着多个标签页、或者误触都会重复触发 —— 魔术包本身无害，
    但没必要让局域网被广播刷屏。限频放在服务端：前端禁按钮只管当前页面。
    """

    def __init__(self, cooldown: float = 10.0,
                 window: float = 30.0, quota: int = 10):
        self.cooldown = cooldown
        self.window = window
        self.quota = quota
        self._last: dict[str, float] = {}
        self._recent: list[float] = []
        self._lock = threading.Lock()

    def acquire(self, key: str, now: float | None = None) -> float:
        """放行返回 0.0；否则返回还需要等几秒（调用方拿去写提示）。"""
        now = time.time() if now is None else now
        with self._lock:
            wait = self.cooldown - (now - self._last.get(key, 0.0))
            if wait > 0:
                return wait
            recent = [t for t in self._recent if now - t < self.window]
            if len(recent) >= self.quota:
                return self.window - (now - recent[0]) + 0.001
            recent.append(now)
            self._recent = recent
            self._last[key] = now
            return 0.0
