# -*- coding: utf-8 -*-
"""
运行时装配

把「配置 + 路由器客户端 + 同步器」装成一个 Node，并提供一个能力：
**网页改完设置能热生效**（重建 Config 与路由器对象，同步器原地换掉）。

配置优先级：网页设置(settings.json) > 环境变量 > 代码默认值

这里所有会碰路由器的动作都走 `syncer.ensure_login()` 而不是 `router.login()` ——
因为 ensure_login 带**指数退避**。设备连续 3 次密码错就锁 admin 账号，
网页这种"刷新一下就试一次"的入口如果绕过退避，很容易把账号锁死。
"""
from __future__ import annotations

import ipaddress
import logging
import os
import threading
import time

from . import (devtypes, discover, events, notify, notify_events, notify_presets,
               router_info, settings as st, tasks as tk, trustlist, wol)
from .config import load_config
from .router import HuaweiRouter, NotLoggedIn, RouterError
from .sync import Syncer

log = logging.getLogger("ipv6sync.node")


def make_router(cfg) -> HuaweiRouter:
    return HuaweiRouter(base=cfg.base_url, username=cfg.username,
                        password=cfg.password, session_file=cfg.session_file,
                        timeout=cfg.timeout)


def _truthy(v) -> bool:
    """固件的开关字段可能是 bool / 1 / "0" / "false" 等各种形态，统一判定。

    注意 bool("0") 是 True，直接 bool() 会把固件用字符串表示的「关」误判成开。
    """
    if isinstance(v, bool):
        return v
    return str(v or "").strip().lower() not in ("", "0", "false", "off", "no", "none")


def _port_label(p) -> str:
    """端口值 → 展示文本：-1/空 = 全部（修改日志的端口列用）。"""
    s = str(p or "").strip()
    return "全部" if s in ("", "-1") else s


def _is_kid(h: dict) -> bool:
    """该设备是否被路由器「儿童上网保护」管控。

    HostInfo 里带管控标记的字段有两个（固件版本不同留哪个不定）：
    ParentControlEnable（开关）与 MacFilterID（管控档案 ID，空/"0" 表示未加入）。
    """
    if _truthy(h.get("ParentControlEnable")):
        return True
    mfid = str(h.get("MacFilterID") or "").strip()
    return mfid not in ("", "0")


def _iface_of(h: dict) -> str:
    """接入方式。固件 InterfaceType 的取值：LAN / 2.4GHz / 5GHz / DC / wifi7-mld / PLC。

    这些值是固件自己判定的（有线走 LAN，无线带频段），比自己按 IP 或名字猜可靠。
    """
    return str(h.get("InterfaceType") or "").strip()


def _brand_of(h: dict) -> str:
    """设备品牌。固件带两处：DevBrands 是自动识别的，ActualManu 是用户改过的
    （没改过时值为 "Default"）—— 有手改的就用手改的。"""
    man = str(h.get("ActualManu") or "").strip()
    if man and man.lower() != "default":
        return man
    return str(h.get("DevBrands") or "").strip()


# AccessRecord 在不同固件上有几种写法，能认几种认几种
_ACCESS_FORMATS = ("%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S", "%Y-%m-%d %H:%M",
                   "%Y-%m-%dT%H:%M:%S", "%Y%m%d%H%M%S")


def _parse_access(raw):
    """把 AccessRecord 解析成 datetime；认不出来返回 None（界面上就不显示时长）。"""
    import datetime as _dt
    txt = str(raw or "").strip()
    if not txt:
        return None
    if txt.isdigit():
        # 可能是秒或毫秒时间戳
        v = int(txt)
        if v > 10 ** 11:
            v //= 1000
        try:
            return _dt.datetime.fromtimestamp(v)
        except (OverflowError, OSError, ValueError):
            return None
    for fmt in _ACCESS_FORMATS:
        try:
            return _dt.datetime.strptime(txt, fmt)
        except ValueError:
            continue
    return None


def _online_secs(h: dict, now=None):
    """已在线秒数（AccessRecord 到现在的差值）。取不到就是 None，界面显示占位。"""
    import datetime as _dt
    start = _parse_access(h.get("AccessRecord"))
    if start is None:
        return None
    now = now or _dt.datetime.now()
    try:
        return max(0, int((now - start).total_seconds()))
    except TypeError:          # 时区不同无法相减
        return None


def _kbps_of(h: dict, key: str) -> int:
    """上下行实时速率。固件这就是 KB/s（固件自己显示时 ×8 转成 Kbps）。"""
    try:
        return max(0, int(float(h.get(key) or 0)))
    except (TypeError, ValueError):
        return 0


def _cfg(node) -> object:
    """拿当前配置。

    单元测试里会用 `Node.__new__` 只装配 syncer + router（没有 `cfg` 属性），
    所以一律走这个函数，不要直接写 `node.cfg`。
    """
    try:        return node.cfg
    except AttributeError:
        return node.syncer.cfg


# --------------------------------------------------------------------------
# Mesh 拓扑：子路由本身 / 谁挂在谁下面
#
# 依据（免登录逆向固件前端，chunk 9 = 终端页 + main.js 路由表）：
#   * 接口 `device/topology`（路由表里 `topology:"device/topology"`，即 /api/device/topology）
#   * 返回的顶层数组**每一项是一个路由器节点**：
#         {MACAddress, HiLinkType, ConnectedDevices:[...], routerSelf}
#   * `"Device" === node.HiLinkType` → 这条是路由器 / 子路由；终端设备的 HiLinkType 不是 Device
#   * `selfDevice = topology 里 routerSelf == 1 的那条` → 主路由自己，
#     `childDevices = 去掉 selfDevice` → 所有子路由
#   * 节点下挂的终端在它自己的 ConnectedDevices 里（多层 Mesh 可递归）
#
# 没有真机返回样本，所以字段名一律多重兜底；认不出就当「这台固件没有拓扑」：
# 上层只做 VendorClassID 排除、不显示分组 —— 绝不因为一个新功能把设备列表搞空。
# --------------------------------------------------------------------------

_MAC_KEYS = ("MACAddress", "MacAddress", "macAddress", "Mac", "mac", "MAC")
_CHILD_KEYS = ("ConnectedDevices", "connectedDevices", "ChildDevices", "childDevices",
               "SubDevices", "subDevices", "Devices", "devices")
_HITYPE_KEYS = ("HiLinkType", "hilinktype", "hiLinkType", "LinkType")
_SELF_KEYS = ("routerSelf", "RouterSelf", "isSelf", "Self")
_HLINK_DEVICE = "device"

# HostInfo 里路由器类设备的 VendorClassID 关键词。
# 固件给子路由算速率时就是这么排的 —— 这是**不依赖拓扑接口**的第二套判据。
_NODE_VENDOR_HINTS = ("router", "plcap", "repeater")

# 拓扑缓存的存活时间（秒）。成功一次管一分钟，失败一次管五分钟：
# 老固件没有这个接口时，别每次刷新设备页都去撞一次 404。
_MESH_TTL = 60
_MESH_FAIL_TTL = 300


def _pick(d: dict, keys) -> object:
    """按候选键名取值，第一个非空的就是它（固件不同版本字段名会飘）。"""
    for k in keys:
        if k in d:
            v = d[k]
            if v is not None and v != "":
                return v
    return ""


def _as_list(v, depth: int = 0) -> list:
    """把「list / {data:[...]} / 单个对象」统一成 list。

    华为这套接口有时直接返回裸数组，有时外面套一层 data —— 两种都得认。
    """
    if isinstance(v, list):
        return v
    if isinstance(v, dict) and depth < 3:
        for k in ("data", "Data", "devices", "Devices", "topology", "Topology",
                  "nodes", "Nodes", "result", "list"):
            if k in v:
                got = _as_list(v[k], depth + 1)
                if got:
                    return got
        return [v]
    return []


def _fmt_mac(key: str) -> str:
    """12 位 hex → AA:BB:CC:DD:EE:FF（只用于显示，内部一律用 norm_mac）。"""
    if len(key) != 12:
        return key
    return ":".join(key[i:i + 2] for i in range(0, 12, 2)).upper()


def _looks_like_node(h: dict) -> bool:
    """HostInfo 里这条是不是路由器类设备（子路由 / 电力线 AP / 中继）。

    拓扑读不到时就靠这条把子路由从设备列表里排掉。判据与固件一致
    （VendorClassID 含 router / PLCAP / repeater），所以不会比固件自己更激进。
    """
    v = str(h.get("VendorClassID") or h.get("VendorClassId") or "").lower()
    return any(x in v for x in _NODE_VENDOR_HINTS)


def parse_topology(tree):
    """`device/topology` → (节点列表, {终端 MAC: 所在节点 MAC})。

    节点列表按「主路由在前、其余保持固件顺序」排。返回 (None, {}) 表示这份
    数据里认不出任何路由器节点（接口不存在 / 结构变了）—— 调用方据此降级。
    """
    nodes: list[dict] = []
    by_key: dict[str, dict] = {}
    owner: dict[str, str] = {}

    def walk(item, parent: str):
        if not isinstance(item, dict):
            return
        key = discover.norm_mac(str(_pick(item, _MAC_KEYS) or ""))
        hitype = str(_pick(item, _HITYPE_KEYS) or "").strip().lower()
        is_self = _truthy(_pick(item, _SELF_KEYS))
        if hitype == _HLINK_DEVICE or is_self:
            if key and key not in by_key:
                node = {
                    "key": key,
                    "mac": _fmt_mac(key),
                    "name": str(_pick(item, ("HostName", "DevName", "DeviceName",
                                             "Name", "nickname")) or "").strip(),
                    "model": str(_pick(item, ("DeviceModel", "Model", "ProductName",
                                              "DeviceTypeName", "DeviceType")) or "").strip(),
                    "self": is_self,
                    "parent": parent,
                }
                by_key[key] = node
                nodes.append(node)
            parent = key or parent          # 它下面挂的东西归它
        for child in _as_list(_pick(item, _CHILD_KEYS)):
            if not isinstance(child, dict):
                continue
            ckey = discover.norm_mac(str(_pick(child, _MAC_KEYS) or ""))
            ctype = str(_pick(child, _HITYPE_KEYS) or "").strip().lower()
            if ctype == _HLINK_DEVICE or _truthy(_pick(child, _SELF_KEYS)):
                walk(child, parent)         # 嵌套在里面的子路由，继续往下走
            elif ckey and ckey != key:
                owner.setdefault(ckey, parent)

    for item in _as_list(tree):
        walk(item, "")

    if not nodes:
        return None, {}
    nodes.sort(key=lambda n: 0 if n["self"] else 1)
    return nodes, owner


def _parse_blacklist(res) -> list:
    """从 wlanfilterenhance 响应里抽 WiFi MAC 黑名单（2.4G/5G 各一份，合并去重）。

    固件返回结构随版本变化（整体是列表还是字典、条目是对象还是纯 MAC 字符串
    都可能），这里做宽容解析：递归找键名含 BMAC 的字段，条目尽量带出主机名
    和频段。同名 MAC 跨频段重复出现时合并为一行，频段用 "+" 拼接。
    """
    rows: dict[str, dict] = {}

    def band_label(node: dict, fallback: str) -> str:
        for k in ("WifiModulename", "wifiModulename", "FrequencyBand",
                  "WifiBand", "Band", "band"):
            v = node.get(k)
            if v:
                return str(v)
        return fallback

    def add(mac, name, band: str):
        mac = str(mac or "").strip().upper()
        if not mac:
            return
        cur = rows.setdefault(mac, {"mac": mac, "name": "", "band": ""})
        if name and not cur["name"]:
            cur["name"] = str(name)
        if band and band not in cur["band"]:
            cur["band"] = (cur["band"] + "+" + band) if cur["band"] else band

    def walk(node, band: str):
        if isinstance(node, list):
            for x in node:
                walk(x, band)
            return
        if not isinstance(node, dict):
            return
        b = band_label(node, band)
        for key, val in node.items():
            if "bmac" in str(key).lower():
                entries = val
                if isinstance(entries, dict):      # 个别固件再包一层字典
                    entries = [v for v in entries.values() if isinstance(v, list)]
                    entries = [e for lst in entries for e in lst]
                if isinstance(entries, str):
                    entries = [entries]
                for e in entries if isinstance(entries, list) else []:
                    if isinstance(e, dict):
                        mac = (e.get("MACAddress") or e.get("MacAddress")
                               or e.get("BMACAddress") or e.get("mac"))
                        name = (e.get("ActualName") or e.get("HostName")
                                or e.get("hostname") or e.get("devName")
                                or e.get("DeviceName"))
                        add(mac, name or "", b)
                    else:
                        add(e, "", b)
            else:
                walk(val, b)

    walk(res, "")
    return sorted(rows.values(), key=lambda r: r["mac"])


class Node:
    def __init__(self, cfg):
        self.settings_file = cfg.settings_file or st.settings_path()
        self.cfg = cfg
        self.overlay = st.load_overlay(self.settings_file)
        self.router = make_router(cfg)
        if self.router.session_file and self.router.load():
            log.info("已加载既有会话（%s）", self.router.session_file)
        self.syncer = Syncer(cfg, self.router)
        # 只保护"替换 self.cfg / self.router"这几行本身；
        # 真正跑一轮同步的互斥由 syncer.lock 负责。
        self._lock = threading.RLock()
        # 网络唤醒的限频闸（同一台设备 10 秒内只发一次）
        self._wol_gate = wol.Throttle(cooldown=10.0)
        # 计划任务：调度在本地算，路由器只负责执行。
        # get_router 用 lambda —— 网页改了密码会重建 router，调度器不能握着旧会话。
        self.tasks = tk.Tasks(lambda: self.router,
                              tk.tasks_path(self.settings_file),
                              guard=lambda: self.syncer.lock)
        # 任务执行结果也走通知事件（成功 / 失败 / 已错过）
        self.tasks.on_event = lambda code, text, subject: \
            notify_events.dispatch(self.cfg, code, text, subject=subject)

    # ---------------- 只读视图 ----------------

    def snapshot(self) -> dict:
        return self.syncer.snapshot()

    def settings_view(self) -> list:
        with self._lock:
            return st.view(self.cfg, self.overlay)

    def overview(self) -> dict:
        with self._lock:
            cfg, ov = self.cfg, self.overlay
            return {
                "router_base": cfg.base_url,
                "router_user": cfg.username,
                "router_host": cfg.host,
                "password_from": cfg.password_source or (
                    "（未配置，只复用会话）" if not cfg.password else "环境变量"),
                "password_set": bool(cfg.password),
                "settings_file": self.settings_file,
                "settings_keys": sorted(ov),
                "session_file": cfg.session_file,
                "rules": [{
                    "name": r.name,
                    "port": "全部" if r.port in (None, -1) else r.port,
                    "remote_ip": r.remote_ip,
                    "mac": r.mac or "",
                } for r in cfg.rules],
            }

    # ---------------- 改设置 ----------------

    def save_settings(self, patch: dict) -> dict:
        """合并 → 校验 → 落盘 → 热重配。返回 {"overview":..,"settings":..,"notes":[..]}"""
        if not isinstance(patch, dict) or not patch:
            raise st.SettingsError("没有要保存的内容")

        with self._lock:
            merged = dict(self.overlay)
            merged.update(patch)
            clean = st.validate_overlay(merged)          # 坏值在这里被拒

            old = self.cfg
            st.save_overlay(clean, self.settings_file)

            # 重新装配：环境变量打底，覆盖层盖上去 —— 与启动时的顺序完全一致
            new_cfg = load_config([])
            notes = []

            # 换了地址 / 用户名 / 密码 → 旧会话对新身份没意义，直接丢掉
            cred_changed = (new_cfg.host != old.host
                            or new_cfg.username != old.username
                            or new_cfg.password != old.password)
            if cred_changed:
                self._drop_session(old.session_file)
                notes.append("路由器地址/账号/密码有变动，已丢弃旧会话，稍后按新账号重新登录")

            new_router = make_router(new_cfg)
            if not cred_changed and new_router.load():
                notes.append("已复用既有会话")

            self.cfg = new_cfg
            self.overlay = clean
            self.router = new_router
            self.syncer.reconfigure(new_cfg, new_router)
            # 换了路由器：拓扑缓存与「这台没有拓扑」的判断都得重来，
            # 否则换到一台支持的机器上还得等容器重启才认。
            self._mesh_cache = None
            self._mesh_off = False

            log.info("网页设置已应用（%d 项变更）", len(patch))
            return {"overview": self.overview(),
                    "settings": st.view(new_cfg, clean),
                    "notes": notes}

    @staticmethod
    def _drop_session(path: str | None):
        if path and os.path.exists(path):
            try:
                os.remove(path)
                log.info("已删除旧会话 %s", path)
            except OSError as e:
                log.warning("删不掉旧会话 %s：%s", path, e)

    # ---------------- 动路由器 ----------------

    def _logged_in(self) -> str | None:
        """保证处于登录态；不行就返回错误说明（不抛异常，方便直接回给网页）。"""
        if self.syncer.ensure_login():
            return None
        left = self.syncer.login_backoff_remaining()
        base = self.syncer.last_error or "未知原因"
        if left > 0:
            # 网页上点按钮最容易踩这个：退避期间什么都不会发生，得说清为什么，
            # 否则用户会以为坏了，然后一直点。
            return (f"登录退避中，还需 {left} 秒才会再试（上次失败：{base}）。"
                    f"这是为了不让密码连错 3 次锁死管理员账号，先确认密码对不对。")
        return base

    def sync_now(self) -> dict:
        """立即跑一轮同步（与主循环互斥）。"""
        log.info("网页触发：立即同步一次")
        self.syncer.trigger = "手动同步"
        return self.syncer.tick()

    def test_connection(self) -> dict:
        """测试路由器连通性与账号是否可用：登录 + 读设备信息。"""
        with self.syncer.lock:
            err = self._logged_in()
            if err:
                return {"ok": False, "error": err}
            try:
                info = self.router.get("deviceinfo") or {}
            except RouterError as e:
                return {"ok": False, "error": str(e)}
            return {"ok": True, "device": self._device_summary(info)}

    @staticmethod
    def _device_summary(info: dict) -> dict:
        return {
            "product": info.get("ProductName") or info.get("DeviceName") or "",
            "model": info.get("DeviceModel") or info.get("Model") or "",
            "sn": info.get("SerialNumber") or info.get("Sn") or "",
            "software": info.get("SoftwareVersion") or "",
        }

    def whitelist(self) -> dict:
        """实读 IPv6 防火墙白名单，附带规则列表与设备数据（弹窗选址用）。"""
        with self.syncer.lock:
            err = self._logged_in()
            if err:
                return {"ok": False, "error": err}
            try:
                enabled = trustlist.is_enabled(self.router)
                # 顺手把总开关状态回填给同步引擎：这是**实读**的结果，而引擎里
                # 那个值原来要等一整轮 tick 跑完才有 —— 首次启动刚打开控制台
                # 时页头会显示「待同步」，其实同一屏的白名单卡已经读回来了。
                # 只回填显示用的 firewall_on，**不碰** _fw_seen：那个是给
                # 「开关在路由器端被人改动」的变更检测做基准的，不能混。
                self.syncer.firewall_on = enabled
                return {"ok": True,
                        "enabled": enabled,
                        "max": trustlist.MAX_ENTRIES,
                        "entries": trustlist.list_entries(self.router),
                        "rules": [{"name": r.name, "mac": r.mac or "",
                                   "port": "全部" if r.port in (None, -1)
                                           else r.port,
                                   "remote_ip": r.remote_ip}
                                  for r in self.cfg.rules],
                        "hosts": self._host_rows()}
            except RouterError as e:
                return {"ok": False, "error": str(e)}

    def set_firewall(self, on: bool) -> dict:
        """开 / 关 IPv6 防火墙总开关（网页上的显式动作，不自动做）。"""
        with self.syncer.lock:
            err = self._logged_in()
            if err:
                return {"ok": False, "error": err}
            try:
                res = trustlist.set_enabled(self.router, on)
            except RouterError as e:
                return {"ok": False, "error": str(e)}
            if not trustlist.ok(res):
                return {"ok": False, "error": f"设备拒绝：{res}"}
            self.syncer.firewall_on = on
            self.syncer._fw_seen = on      # 网页动作自己记日志，别让下轮重复记
            self.syncer._log_event("fw", trigger="网页", device="（全局）",
                                   entry="—",
                                   addr="总开关已开启" if on
                                   else "总开关已关闭（进入待机）", port="")
            return {"ok": True, "enabled": on}

    def reset_counters(self) -> dict:
        """清零累计写入计数（网页「重置累计写入」按钮，需在网页上显式确认）。"""
        with self.syncer.lock:
            self.syncer.counters.reset()
            self.syncer.counters.flush()
            log.info("累计写入计数已从网页重置清零")
            return {"ok": True, "counters": self.syncer.counters.payload()}

    # ---------------- 修改日志（文件即数据，见 events.py） ----------------

    def events_list(self) -> dict:
        """现读 /data/events.jsonl（时间正序返回，前端倒序展示 + 过滤分页）。"""
        return {"ok": True, "events": events.read(self.cfg.state_file),
                "max": self.cfg.events_max}

    def events_clear(self) -> dict:
        """一键清空修改日志（网页上已二次确认；不影响白名单和同步）。"""
        events.clear(self.cfg.state_file)
        return {"ok": True}

    def set_events_max(self, value) -> dict:
        """改保留条数：立即裁剪并落盘（值存 settings.json 的 LOG_MAX，表单里隐藏）。"""
        try:
            n = int(value)
        except (TypeError, ValueError):
            raise st.SettingsError("保留条数必须是数字")
        if not 10 <= n <= 200:
            raise st.SettingsError("保留条数必须在 10 ~ 200 之间")
        with self._lock:
            merged = dict(self.overlay)
            merged["LOG_MAX"] = n
            clean = st.validate_overlay(merged)
            st.save_overlay(clean, self.settings_file)
            self.overlay = clean
            self.cfg.events_max = n
        # 立即按新上限裁剪一次（调小时马上生效，不等下次写入）
        path = events.events_path(self.cfg.state_file)
        try:
            with events._lock:
                events._trim(path, n)
        except OSError as e:
            log.warning("按新上限裁剪同步记录失败：%s", e)
        log.info("同步记录保留上限改为 %d 条", n)
        return {"ok": True, "max": n}

    def test_notify(self) -> dict:
        """向所有启用渠道发一条测试消息（不看总开关 / 事件订阅 / 静默时段）。"""
        results = notify_events.dispatch(
            self.cfg, "test",
            "这是一条来自 HiRouterCenter 的测试消息。收到它说明渠道是通的。",
            title="测试通知", force=True)
        if not results:
            return {"ok": False,
                    "error": "还没有启用的通知渠道，先在「通知」页添加一个"}
        failed = [f"{r['name']}: {r['error']}" for r in results
                  if not r.get("ok")]
        return {"ok": not failed, "results": results, "error": "; ".join(failed)}

    # ---------------- 通知：渠道 / 事件 / 策略 / 历史 ----------------

    def notify_view(self) -> dict:
        """「通知」页要的全部数据（一次拿齐，省三次往返）。"""
        with self._lock:
            cfg = self.cfg
            chans = notify.channels(cfg)
        return {
            "ok": True,
            "enabled": bool(getattr(cfg, "notify_enabled", True)),
            "quiet": getattr(cfg, "notify_quiet", "") or "",
            "dedupe": notify_events.dedupe_window(cfg),
            "history_max": notify_events.history_max(cfg),
            "history_choices": list(notify_events.HISTORY_CHOICES),
            "history_limit": notify_events.HISTORY_MAX_LIMIT,
            "channels": chans,
            "events": notify_events.events_table(cfg),
            "presets": notify_presets.specs(),
        }

    def _write_overlay(self, patch: dict) -> None:
        """只改设置文件里的某几个键并热生效。

        调用方需已持锁（RLock 可重入）。和 save_settings 的区别：**不重建路由器
        连接、不清同步状态** —— 改个通知渠道不该把一轮同步的进度清掉。
        """
        merged = dict(self.overlay)
        merged.update(patch)
        clean = st.validate_overlay(merged)
        st.save_overlay(clean, self.settings_file)
        new_cfg = load_config([])
        self.overlay = clean
        self.cfg = new_cfg
        self.syncer.cfg = new_cfg

    def save_channels(self, items: list) -> dict:
        """整份渠道列表保存（前端「加 / 改 / 删」都走这一条，避免并发错位）。"""
        try:
            with self._lock:
                kept = notify.save(self.cfg, items)
                self._write_overlay({st.CHANNELS_KEY: kept})
        except ValueError as e:
            raise st.SettingsError(str(e))
        log.info("通知渠道已保存：%d 个", len(kept))
        return {"ok": True, "channels": kept}

    def test_channel(self, channel: dict) -> dict:
        """按界面上**当前填的**配置测一条（不用先保存才能测）。"""
        try:
            ch = notify.normalize_channel(channel)
        except ValueError as e:
            return {"ok": False, "error": str(e)}
        miss = notify_presets.missing_fields(ch["type"], ch["config"])
        if miss:
            return {"ok": False, "error": "还没填：" + "、".join(miss)}
        ok, err = notify.send_test(self.cfg, ch)
        return {"ok": ok, "error": err}

    def save_notify_policy(self, patch: dict) -> dict:
        """总开关 / 静默时段 / 去重窗口 / 历史条数 / 事件订阅。"""
        want: dict = {}
        if "enabled" in patch:
            want[st.BY_KEY["NOTIFY_ENABLED"].key] = bool(patch["enabled"])
        if "quiet" in patch:
            want["NOTIFY_QUIET"] = patch["quiet"]
        if "dedupe" in patch:
            want["NOTIFY_DEDUPE"] = patch["dedupe"]
        if "history_max" in patch:
            want["NOTIFY_HISTORY_MAX"] = patch["history_max"]
        if "events" in patch:
            raw = patch["events"]
            if isinstance(raw, list):
                raw = {str(e.get("code")): bool(e.get("on"))
                       for e in raw if isinstance(e, dict)}
            want[st.NOTIFY_EVENTS_KEY] = notify_events.normalize_events(raw)
        if not want:
            raise st.SettingsError("没有要保存的内容")
        with self._lock:
            self._write_overlay(want)
        log.info("通知策略已更新：%s", ", ".join(sorted(want)))
        return {"ok": True, **self.notify_view()}

    def notify_history(self) -> dict:
        cfg = self.cfg
        rows = notify_events.read_history(cfg)
        return {"ok": True, "items": rows[-notify_events.history_max(cfg):],
                "max": notify_events.history_max(cfg),
                "limit": notify_events.HISTORY_MAX_LIMIT}

    def clear_notify_history(self) -> dict:
        notify_events.clear_history(self.cfg)
        return {"ok": True}

    def reset_notify_dedupe(self) -> dict:
        notify_events.reset_dedupe()
        return {"ok": True}

    # ---------------- 路由器信息卡 / 快捷操作 ----------------

    def router_info(self) -> dict:
        """首页信息卡的数据（型号 / 运行时长 / WAN 地址 / Wi-Fi 名称…）。"""
        with self.syncer.lock:
            try:
                info = router_info.collect(self.router)
            except RouterError as e:
                log.warning("读取路由器信息失败：%s", e)
                return {"ok": False, "error": "路由器暂时没有响应"}
            hosts = []
            try:
                hosts = self._host_rows() if self.syncer.ensure_login() else []
            except RouterError:
                hosts = []
            online = sum(1 for h in hosts if h.get("active"))
            return {"ok": True, "info": info, "hosts_total": len(hosts),
                    "hosts_online": online,
                    "firewall_on": self.syncer.firewall_on}

    def set_host_type(self, mac: str, type_id: str) -> dict:
        """手改某台设备的类型（空 / unknown = 清掉手改，回到自动识别）。"""
        mac = (mac or "").strip().upper()
        if not mac:
            raise st.SettingsError("缺少设备 MAC")
        tid = (type_id or "").strip()
        if tid and tid != "unknown" and tid not in devtypes.TYPE_IDS:
            raise st.SettingsError(f"不认识的设备类型：{tid}")
        devtypes.set_type(self.cfg.state_file, mac, tid or "unknown")
        return {"ok": True, "mac": mac, "type": tid or "unknown"}

    # ---------------- 设备卡上的三个动作 ----------------
    # 全部逆向自固件前端（chunk 9 = 终端页），接口与 payload 一致：
    #   改名   POST system/changedevicename {action:"update", data:[{ActualName, ID}]}
    #   限速   POST app/qosclass_host       （整个 HostInfo 条目，改 DeviceMax*Rate）
    #   黑名单 POST ntwk/wlanfilterenhance  （整份 2.4G/5G 过滤配置，改 W/B 名单）

    def _host_raw(self, mac: str) -> dict:
        """按 MAC 取 HostInfo 原始条目（写操作的入参要整条回传，所以不能用精简行）。"""
        key = str(mac or "").strip().upper()
        if not key:
            raise st.SettingsError("缺少设备 MAC")
        try:
            hosts = self.router.get("HostInfo") or []
        except RouterError as e:
            raise st.SettingsError(f"读不到设备列表：{e}") from e
        for h in hosts:
            if str(h.get("MACAddress") or "").strip().upper() == key:
                return h
        raise st.SettingsError("设备列表里找不到这台设备，刷新一下再试")

    def rename_host(self, mac: str, name: str) -> dict:
        """改设备名。写的是路由器的 ActualName —— 手机/路由器后台看到的同一个名字。"""
        name = str(name or "").strip()
        if not name:
            raise st.SettingsError("设备名称不能为空")
        if len(name) > 20:
            raise st.SettingsError("设备名称最多 20 个字")
        with self.syncer.lock:
            err = self._logged_in()
            if err:
                return {"ok": False, "error": err}
            try:
                h = self._host_raw(mac)
                hid = h.get("ID")
                if hid in (None, ""):
                    return {"ok": False, "error": "路由器没给出这台设备的编号，改不了名"}
                res = self.router.post("system/changedevicename",
                                       [{"ActualName": name, "ID": hid}],
                                       action="update")
            except RouterError as e:
                log.warning("改设备名失败：%s", e)
                return {"ok": False, "error": "路由器没有响应，改名没成功"}
            if not trustlist.ok(res):
                return {"ok": False, "error": f"设备拒绝：{res}"}
            return {"ok": True, "name": name}

    def set_host_limit(self, mac: str, up_kbps: int = 0, down_kbps: int = 0) -> dict:
        """按设备限速（QoS）。0 表示不限；两个都为 0 时把这条设备的限速整个关掉。

        走的是固件自己的 qosclass_host：把 HostInfo 整条回传，只改三个字段。
        """
        try:
            up = max(0, int(up_kbps or 0))
            down = max(0, int(down_kbps or 0))
        except (TypeError, ValueError):
            raise st.SettingsError("限速值要填数字") from None
        if up > 1024 * 1024 or down > 1024 * 1024:
            raise st.SettingsError("限速值太大了")
        with self.syncer.lock:
            err = self._logged_in()
            if err:
                return {"ok": False, "error": err}
            try:
                item = dict(self._host_raw(mac))
                item["DeviceMaxUpLoadRate"] = up
                item["DeviceMaxDownLoadRate"] = down
                item["DeviceDownRateEnable"] = 1 if (up or down) else 0
                res = self.router.post("app/qosclass_host", item)
            except RouterError as e:
                log.warning("下发限速失败：%s", e)
                return {"ok": False, "error": "路由器没有响应，限速没下发"}
            if not trustlist.ok(res):
                return {"ok": False, "error": f"设备拒绝：{res}"}
            return {"ok": True, "up_kbps": up, "down_kbps": down}

    @staticmethod
    def _macs_of(entries) -> list:
        """把名单里的条目统一成 [{"HostName","MACAddress"}]，纯 MAC 字符串也认。"""
        out = []
        for e in entries or []:
            if isinstance(e, dict):
                m = str(e.get("MACAddress") or "").strip().upper()
                if m:
                    out.append({"HostName": e.get("HostName") or "",
                                "MACAddress": e.get("MACAddress")})
            else:
                m = str(e or "").strip().upper()
                if m:
                    out.append({"HostName": "", "MACAddress": m})
        return out

    def set_host_blacklist(self, mac: str, on: bool = True) -> dict:
        """加入 / 移出 WiFi MAC 黑名单（2.4G、5G 两份名单要一起改）。

        ⚠️ 这是 WLAN 层的过滤：只对无线设备生效，有线设备不经过它。
        且必须路由器上「MAC 地址过滤」总开关是开的，否则固件自己也会拒绝。
        """
        mac = str(mac or "").strip().upper()
        if not mac:
            raise st.SettingsError("缺少设备 MAC")
        with self.syncer.lock:
            err = self._logged_in()
            if err:
                return {"ok": False, "error": err}
            try:
                data = self.router.get("ntwk/wlanfilterenhance")
            except RouterError as e:
                log.warning("读 MAC 过滤配置失败：%s", e)
                return {"ok": False, "error": "读不到路由器的 MAC 过滤配置"}
            bands = data if isinstance(data, list) else ([data] if isinstance(data, dict) else [])
            if not bands:
                return {"ok": False, "error": "路由器的 MAC 过滤配置是空的（这台固件可能不支持）"}
            head = bands[0] if isinstance(bands[0], dict) else {}
            if not _truthy(head.get("MACAddressControlEnabled")):
                return {"ok": False,
                        "error": "路由器上的「MAC 地址过滤」总开关没开，先打开才能拉黑设备"}
            host_name = ""
            try:
                host_name = discover.host_display_name(self._host_raw(mac))
            except st.SettingsError:
                pass
            entry = {"HostName": host_name, "MACAddress": mac}
            for band in bands:
                if not isinstance(band, dict):
                    continue
                wl = [e for e in self._macs_of(band.get("WMACAddresses"))
                      if e["MACAddress"].upper() != mac]
                bl = [e for e in self._macs_of(band.get("BMACAddresses"))
                      if e["MACAddress"].upper() != mac]
                if on:
                    bl.append(entry)
                else:
                    wl.append(entry)
                band["WMACAddresses"] = wl
                band["BMACAddresses"] = bl
            if on and len(self._macs_of(bands[0].get("BMACAddresses"))) > 32:
                return {"ok": False, "error": "黑名单已经满了（最多 32 台），先删几台再加"}
            try:
                res = self.router.post("ntwk/wlanfilterenhance", bands)
            except RouterError as e:
                log.warning("下发黑名单失败：%s", e)
                return {"ok": False, "error": "路由器没有响应，黑名单没下发"}
            if not trustlist.ok(res):
                return {"ok": False, "error": f"设备拒绝：{res}"}
            return {"ok": True, "blocked": bool(on)}

    # 手动操作后按动作挂静默期：刚重启的路由器别马上去读，否则刷一串假失败
    _QUIET = {"reboot": 240, "redial": 150, "channel": 60, "wifi_power": 20}

    def router_action(self, kind: str, value=None) -> dict:
        """首页信息卡上的四个快捷操作：重启 / 重拨 / 功率模式 / 信道优化。"""
        kind = (kind or "").strip()
        if kind not in self._QUIET:
            raise st.SettingsError("不认识的操作")
        task = {"kind": kind}
        if kind == "wifi_power":
            try:
                mode = int(value)
            except (TypeError, ValueError):
                raise st.SettingsError("功率模式要选一个档位") from None
            if mode not in tk.POWER_MODES:
                raise st.SettingsError("功率模式档位不对")
            task["params"] = {"power_mode": mode}
        with self.syncer.lock:
            err = self._logged_in()
            if err:
                return {"ok": False, "error": err}
            try:
                res = tk.apply(self.router, task)
            except RouterError:
                log.exception("快捷操作失败：%s", kind)
                return {"ok": False, "error": "路由器没有响应，操作没完成"}
            if res.get("ok"):
                # 两条静默期都要挂：一条管同步循环别马上读路由器，
                # 一条管计划任务别在这期间又冲上去按一次按钮
                self.syncer.defer(self._QUIET[kind], reason=kind)
                self.tasks.defer(self._QUIET[kind])
            return res

    def _power_mode(self):
        """当前 Wi-Fi 功率模式（0/1/2）；读不到返回 None，不额外报错。"""
        try:
            radio = self.router.get("wlanradio")
            if isinstance(radio, dict) and radio.get("PowerMode") is not None:
                return int(radio["PowerMode"])
        except Exception:                       # noqa: BLE001
            pass
        return None

    # ---------------- Mesh 拓扑（子路由分组） ----------------

    def _read_mesh(self):
        """调 `device/topology` 并解析。读不到返回 None（不抛错、不影响设备列表）。"""
        if getattr(self, "_mesh_off", False):
            return None
        try:
            raw = self.router.get("device/topology")
        except NotLoggedIn:
            # 固件用「404 空响应」隐藏它不支持的路径，router 层遇到这个会顺手注销
            # 会话（正常逻辑：令牌失效了别继续拿它撞）。但拓扑只是**探测性**请求，
            # 不能因为它把整个设备页变成「未登录」，所以：
            #   1) 永久记下「这台没有拓扑」，之后不再请求；
            #   2) 立刻重新登录把会话补回来。
            self._mesh_off = True
            log.info("这台路由器没有拓扑接口，设备页不提供按节点筛选")
            if self.syncer.ensure_login():
                log.info("拓扑探测把会话撞掉了，已自动重新登录")
            return None
        except RouterError as e:
            log.info("读拓扑失败（%s），设备页不提供按节点筛选", e)
            return None
        nodes, owner = parse_topology(raw)
        if not nodes:
            # 只打前 300 字符：够定位字段名，又不会把整份拓扑刷进日志
            log.warning("拓扑接口返回的结构认不出来，已跳过 Mesh 分组：%s",
                        str(raw)[:300])
            return None
        return {"nodes": nodes, "owner": owner, "grouped": bool(owner)}

    def _mesh(self):
        """带缓存的拓扑读取。失败也缓存（更久），避免每次刷新都撞一次不存在的接口。"""
        now = time.time()
        hit = getattr(self, "_mesh_cache", None)
        if hit and now - hit[0] < hit[2]:
            return hit[1]
        data = self._read_mesh()
        self._mesh_cache = (now, data, _MESH_TTL if data else _MESH_FAIL_TTL)
        return data

    def _mesh_view(self, raw_hosts=None) -> dict:
        """设备页的分组数据（下拉与节点卡共用）。

        节点名优先用固件拓扑给的，其次同 MAC 那台在 HostInfo 里的名字，最后是型号。
        `grouped` 为假表示拓扑里没有任何终端归属信息 —— 前端就别显示下拉了。
        """
        mesh = self._mesh()
        if not mesh:
            return {"ok": False, "nodes": []}
        raw = raw_hosts if raw_hosts is not None else (self.router.get("HostInfo") or [])
        by_mac: dict[str, dict] = {}
        for h in raw:
            if not isinstance(h, dict):
                continue
            k = discover.norm_mac(str(h.get("MACAddress") or ""))
            if k:
                by_mac.setdefault(k, h)
        out = []
        for n in mesh["nodes"]:
            h = by_mac.get(n["key"]) or {}
            name = (n["name"] or discover.host_display_name(h) or n["model"]
                    or ("主路由" if n["self"] else "") or n["mac"])
            out.append({"key": n["key"], "mac": n["mac"], "name": name,
                        "model": n["model"], "self": n["self"],
                        "parent": n["parent"]})
        return {"ok": True, "grouped": mesh["grouped"], "nodes": out}

    def _host_rows(self, raw_hosts=None) -> list[dict]:
        """HostInfo → 设备行（设备列表页与白名单弹窗共用）。调用方需已登录。

        每行带一个 `type`（设备类型图标用）：用户手改的 > 固件字段 > 关键词猜。
        子路由 / 路由器本身不算终端，这里直接跳过（见 Mesh 拓扑那段注释）。
        """
        rows = []
        # 用 _cfg() 兜底：单元测试里会用 Node.__new__ 只装配 syncer + router
        state_file = _cfg(self).state_file
        manual = devtypes.load(state_file)
        if raw_hosts is None:
            raw_hosts = self.router.get("HostInfo") or []
        mesh = self._mesh()
        nodes = (mesh or {}).get("nodes") or []
        owner = (mesh or {}).get("owner") or {}
        node_keys = {n["key"] for n in nodes}
        for h in raw_hosts:
            if not isinstance(h, dict):
                continue
            key = discover.norm_mac(str(h.get("MACAddress") or ""))
            if key and (key in node_keys or _looks_like_node(h)):
                continue
            addrs = discover.host_candidates(h)
            offline_at = (h.get("OfflineRecord") or "").split("#")[0].strip()
            active = _truthy(h.get("Active"))
            mtype, is_manual = devtypes.resolve(h, manual)
            rows.append({
                "mac": h.get("MACAddress", "") or "",
                "name": discover.host_display_name(h),
                "ipv4": h.get("IPAddress", "") or "",
                "ipv6": addrs,
                "active": active,
                "offline_at": offline_at if (offline_at and not active) else "",
                "kids": _is_kid(h),
                "type": mtype,
                "type_manual": is_manual,
                # ---- 设备卡新增字段（全部来自固件真实返回，缺了就是空/0）----
                "id": h.get("ID"),
                "iface": _iface_of(h),
                "brand": _brand_of(h),
                "online_secs": _online_secs(h) if active else None,
                "down_kb": _kbps_of(h, "DownRate") if active else 0,
                "up_kb": _kbps_of(h, "UpRate") if active else 0,
                # 当前限速（Kbps）。DeviceDownRateEnable 是总开关，关着就当没限速
                "limit_up": (_kbps_of(h, "DeviceMaxUpLoadRate")
                             if _truthy(h.get("DeviceDownRateEnable")) else 0),
                "limit_down": (_kbps_of(h, "DeviceMaxDownLoadRate")
                               if _truthy(h.get("DeviceDownRateEnable")) else 0),
                # 累计收发（固件 RxKBytes / TxKBytes，单位 KB，离线机也保留不清零）。
                # 固件前端自己不用这两个字段（43 个 chunk 里零命中），方向是从真机样本
                # 反推的：离线手机 11.7GB/1.2GB、离线台式机 157GB/3.2GB 都符合
                # 「Rx = 设备接收（↓）、Tx = 设备发送（↑）」。
                "rx_kb": _kbps_of(h, "RxKBytes"),
                "tx_kb": _kbps_of(h, "TxKBytes"),
                # 挂在哪个 Mesh 节点下（节点 MAC）。空 = 直连主路由 / 拓扑里没写
                "node": owner.get(key, ""),
            })
        rows.sort(key=lambda r: r["mac"])
        return rows

    def hosts(self) -> dict:
        """设备列表（在线/离线/儿童上网 + WiFi 黑名单）。"""
        with self.syncer.lock:
            err = self._logged_in()
            if err:
                return {"ok": False, "error": err}
            try:
                raw_hosts = self.router.get("HostInfo") or []
                rows = self._host_rows(raw_hosts)
                mesh = self._mesh_view(raw_hosts)
            except RouterError as e:
                return {"ok": False, "error": str(e)}
            # 黑名单是另一个接口（wlanfilterenhance），失败不拖累设备列表本身
            try:
                blacklist = _parse_blacklist(
                    self.router.get("ntwk/wlanfilterenhance"))
                bl_error = ""
            except RouterError as e:
                blacklist, bl_error = [], str(e)
            # 白名单实读条目（只带名字 / 地址 / 端口）：设备卡上要判断
            # 「这台设备当前地址有没有被放行」—— 手工加在路由器上的条目也算。
            # 读失败不拖累设备列表本身，给空列表（设备卡就回到「未放行」）。
            try:
                entries = [{"name": e.get("Name") or "",
                            "local_ip": e.get("LocalIp") or e.get("Localip") or "",
                            "port": e.get("Port")}
                           for e in trustlist.list_entries(self.router)]
            except Exception as e:                # noqa: BLE001 — 设备列表不该被它拖垮
                log.warning("读白名单条目失败，设备页放行状态降级：%s", e)
                entries = []
            return {"ok": True, "hosts": rows,
                    "blacklist": blacklist, "blacklist_error": bl_error,
                    # Mesh 分组：ok=False 表示这台固件没有可用拓扑（前端隐藏下拉）
                    "mesh": mesh,
                    "lan_prefixes": discover.lan_prefixes(self.router),
                    "entries": entries,
                    # 规则列表顺手带上（纯内存，不额外请求路由器）：
                    # 设备卡上「已放行 xxx」就靠它和设备 MAC 对上
                    "rules": [{"name": r.name, "mac": r.mac or "",
                               "port": "全部" if r.port in (None, -1)
                                       else str(r.port)}
                              for r in _cfg(self).rules],
                    "power_mode": self._power_mode()}

    # ---------------- 网络唤醒（设备列表的「唤醒」按钮） ----------------

    def wake_device(self, data: dict) -> dict:
        """给设备列表里的某台设备发 WOL 魔术包。

        两条约束：

        1. **只认路由器设备档案里出现过的 MAC**。否则这个接口就成了「随便填个
           MAC 就往局域网打广播」的口子。在线/离线设备都能唤醒，覆盖正常用途。
        2. **不判定唤醒成功与否**。发了就是发了 —— 设备开机要多久、路由器设备
           表什么时候刷新，都不是我们能控制的（详见 wol.py 顶部说明）。这里
           只把「发出去了」这件事回报给网页。

        注意不要在持 syncer.lock 的时候发广播：一轮同步正卡在路由器请求上时，
        发个包没必要跟着排队。
        """
        mac = discover.norm_mac(str(data.get("mac") or ""))
        if len(mac) != 12:
            raise st.SettingsError("MAC 格式不对，应为 6 段十六进制（如 3C:7C:3F:11:22:33）")

        with self.syncer.lock:
            err = self._logged_in()
            if err:
                return {"ok": False, "error": err}
            try:
                rows = self._host_rows()
            except RouterError as e:
                return {"ok": False, "error": str(e)}

        hit = next((r for r in rows
                    if discover.norm_mac(r.get("mac") or "") == mac), None)
        if hit is None:
            return {"ok": False,
                    "error": "这个 MAC 不在路由器设备档案里 —— 只能在设备列表里唤醒本机已知的设备"}

        wait = self._wol_gate.acquire(mac)
        if wait > 0:
            return {"ok": False, "throttled": True,
                    "error": f"刚给这台设备发过，{int(wait) + 1} 秒后再试"}

        res = wol.send(hit.get("mac") or mac, hit.get("ipv4") or "")
        label = hit.get("name") or "未知设备"
        if res.get("ok"):
            log.info("已向 %s（%s）发送唤醒包：%d 个广播 → %s", label, hit["mac"],
                     res["sent"], ", ".join(res["targets"]))
        else:
            log.warning("向 %s（%s）发送唤醒包失败：%s", label, hit["mac"],
                        res.get("error"))
        return res

    # ---------------- 计划任务（重启 / 重拨 / 功率模式 / 信道优化） ----------------
    #
    # 分工：**什么时候执行在本地算，路由器只负责「现在做」**。Q7 固件把
    # 「重启计划」「定时重拨」页面裁掉了，只能由本程序到点去按对应的按钮。

    def tasks_view(self) -> dict:
        return self.tasks.view()

    def task_cron_check(self, data: dict) -> dict:
        """弹窗里输 cron 时实时校验：合法给「人话」，不合法给一句能懂的原因。

        纯校验，不落盘、不动调度 —— 单一解析源在后端，前端预览和表格里
        「重复」列显示的句子保证一致。
        """
        from . import cronexpr
        expr = cronexpr.normalize(str(data.get("cron") or ""))
        if not expr:
            return {"ok": False, "error": "还没有填写 cron 表达式"}
        try:
            return {"ok": True, "cron": expr, "human": cronexpr.human(expr)}
        except ValueError as e:
            return {"ok": False, "error": str(e)}

    def tasks_tick(self) -> dict | None:
        return self.tasks.tick()

    def in_quiet(self) -> bool:
        """刚才执行过重启/重拨等动作，路由器可能还没回来 —— 此时同步应当让路。"""
        return self.tasks.quiet_left() > 0

    def task_save(self, data: dict) -> dict:
        try:
            return self.tasks.upsert(data)
        except ValueError as e:
            raise st.SettingsError(str(e))

    def task_delete(self, data: dict) -> dict:
        try:
            return self.tasks.delete(str(data.get("id") or ""))
        except ValueError as e:
            raise st.SettingsError(str(e))

    def task_toggle(self, data: dict) -> dict:
        try:
            return self.tasks.toggle(str(data.get("id") or ""),
                                     bool(data.get("enabled", True)))
        except ValueError as e:
            raise st.SettingsError(str(e))

    def task_run(self, data: dict) -> dict:
        """手动执行一次（页面的「立即执行」）。不需要登录路由器也能排队，
        真正发请求时会走 ensure_login 的退避。"""
        try:
            return self.tasks.run(str(data.get("id") or ""), manual=True)
        except ValueError as e:
            raise st.SettingsError(str(e))

    # ---------------- 白名单规则管理（网页白名单页的弹窗） ----------------

    @staticmethod
    def _rule_from_cfg(r) -> dict:
        """Config 里的 Rule → overlay 存储形态（规则列表增删改的公共底座）。"""
        port = r.port
        return {"name": r.name, "mac": r.mac or "",
                "port": "-1" if port in (None, -1) else str(port),
                "remote_ip": r.remote_ip or "::/0"}

    @staticmethod
    def _rule_payload(data: dict) -> dict:
        """校验网页提交的一条规则，返回规范化后的存储形态。"""
        name = str(data.get("name") or "").strip()
        if not name:
            raise st.SettingsError("服务名称不能为空")
        if len(name) > 48:
            raise st.SettingsError("服务名称最长 48 个字符")
        mac = discover.norm_mac(data.get("mac") or "")
        if not mac:
            raise st.SettingsError(
                "必须选择一台设备 —— 自动维护要跟随设备的地址变化")
        port = str(data.get("port") or "-1").strip() or "-1"
        if port != "-1":
            for tok in port.replace("，", ",").split(","):
                tok = tok.strip()
                if not tok.isdigit() or not 1 <= int(tok) <= 65535:
                    raise st.SettingsError(
                        "放行端口格式不对：多个端口用英文逗号分隔，"
                        "每个 1-65535，或 -1 表示全部端口")
        remote = str(data.get("remote_ip") or "::/0").strip() or "::/0"
        try:
            ipaddress.ip_network(remote, strict=False)
        except ValueError:
            raise st.SettingsError(f"允许来源 {remote!r} 不是合法的网段或地址")
        return {"name": name, "mac": mac, "port": port, "remote_ip": remote}

    def _persist_rules(self, rules: list[dict]) -> None:
        """把规则列表写进 overlay 并热重配（调用方需持 syncer.lock）。"""
        merged = dict(self.overlay)
        merged[st.RULES_KEY] = rules
        clean = st.validate_overlay(merged)          # 坏值在这里被拒
        st.save_overlay(clean, self.settings_file)
        new_cfg = load_config([])
        self.cfg = new_cfg
        self.overlay = clean
        self.syncer.reconfigure(new_cfg, self.router)

    def rules_api(self, data: dict) -> dict:
        """白名单页的规则管理：add / update / remove，改完立即收敛一轮。

        remove 与「改名」都会把旧名字下本程序生成的条目从路由器上删掉 ——
        不然规则没了名字就没人认领，那些条目永远躺在白名单里。
        """
        action = str(data.get("action") or "")
        with self.syncer.lock:
            err = self._logged_in()
            if err:
                return {"ok": False, "error": err}
            try:
                rules = [self._rule_from_cfg(r) for r in self.cfg.rules]
                if action == "add":
                    item = self._rule_payload(data)
                    if any(x["name"] == item["name"] for x in rules):
                        raise st.SettingsError(f"已存在同名规则：{item['name']}")
                    rules.append(item)
                elif action == "update":
                    old = str(data.get("old_name") or "").strip()
                    idx = next((i for i, x in enumerate(rules)
                                if x["name"] == old), None)
                    if idx is None:
                        raise st.SettingsError(f"找不到要修改的规则：{old}")
                    item = self._rule_payload(data)
                    if item["name"] != old and any(
                            x["name"] == item["name"] for x in rules):
                        raise st.SettingsError(f"已存在同名规则：{item['name']}")
                    if item["name"] != old:
                        self._remove_entries_of(old)
                    rules[idx] = item
                elif action == "remove":
                    name = str(data.get("name") or "").strip()
                    idx = next((i for i, x in enumerate(rules)
                                if x["name"] == name), None)
                    if idx is None:
                        raise st.SettingsError(f"找不到要删除的规则：{name}")
                    self._remove_entries_of(name)
                    rules.pop(idx)
                else:
                    raise st.SettingsError("action 必须是 add / update / remove")

                self._persist_rules(rules)
            except st.SettingsError as e:
                return {"ok": False, "error": str(e)}

            if action in ("add", "update"):
                self.syncer.trigger = ("弹窗添加" if action == "add"
                                       else "弹窗修改")
                snap = self.syncer.tick()    # 立即按新规则收敛一轮（含变更通知）
                return {"ok": bool(snap.get("ok", True)),
                        "notes": ["已保存并立即同步"]}
            return {"ok": True, "notes": ["已删除条目及其自动维护规则"]}

    def _remove_entries_of(self, base: str) -> None:
        """把某规则名下的本程序条目从路由器上删掉（需持 syncer.lock）。"""
        old = {e.get("Name"): (e.get("LocalIp") or "", e.get("Port"))
               for e in trustlist.list_entries(self.router)}
        gone = trustlist.remove_stale(self.router, base, set())
        if gone:
            self.syncer.counters.bump(removed=len(gone))
            self.syncer.counters.flush()
            for nm in gone:
                oa, op = old.get(nm, ("", ""))
                self.syncer._log_event("removed", trigger="网页操作",
                                       device=base, entry=nm,
                                       addr=oa, port=_port_label(op))
            log.info("已删除规则 %s 名下的条目：%s", base, ", ".join(gone))

    def delete_whitelist_entry(self, data: dict) -> dict:
        """删除路由器白名单上的一条条目（手工条目的删除按钮）。"""
        entry_id = str(data.get("id") or "").strip()
        name = str(data.get("name") or "").strip()
        with self.syncer.lock:
            err = self._logged_in()
            if err:
                return {"ok": False, "error": err}
            target = None
            for e in trustlist.list_entries(self.router):
                if ((entry_id and e.get("ID") == entry_id)
                        or (not entry_id and name and e.get("Name") == name)):
                    target = e
                    break
            if target is None:
                return {"ok": False,
                        "error": "白名单里找不到这条记录（可能已被删除）"}
            try:
                res = trustlist.delete(self.router, target)
            except RouterError as e:
                return {"ok": False, "error": str(e)}
            if not trustlist.ok(res):
                return {"ok": False, "error": f"设备拒绝：{res}"}
            self.syncer.counters.bump(removed=1)
            self.syncer.counters.flush()
            self.syncer._log_event("removed", trigger="网页操作",
                                   device=target.get("Name") or "（手工条目）",
                                   entry=target.get("Name") or "",
                                   addr=target.get("LocalIp") or "",
                                   port=_port_label(target.get("Port")))
            return {"ok": True}

    def update_whitelist_entry(self, data: dict) -> dict:
        """原地修改路由器白名单上的一条手工条目（不建自动维护规则）。"""
        entry_id = str(data.get("id") or "").strip()
        name = str(data.get("name") or "").strip()
        if not name:
            raise st.SettingsError("服务名称不能为空")
        local_ip = str(data.get("local_ip") or "").strip()
        if not discover.canon(local_ip):
            raise st.SettingsError(f"本地 IP {local_ip!r} 不是合法的 IPv6 地址")
        remote = str(data.get("remote_ip") or "::/0").strip() or "::/0"
        try:
            ipaddress.ip_network(remote, strict=False)
        except ValueError:
            raise st.SettingsError(f"允许来源 {remote!r} 不是合法的网段或地址")
        port = str(data.get("port") or "-1").strip() or "-1"
        if port != "-1":
            for tok in port.replace("，", ",").split(","):
                tok = tok.strip()
                if not tok.isdigit() or not 1 <= int(tok) <= 65535:
                    raise st.SettingsError(
                        "放行端口格式不对：多个端口用英文逗号分隔，"
                        "每个 1-65535，或 -1 表示全部端口")
        with self.syncer.lock:
            err = self._logged_in()
            if err:
                return {"ok": False, "error": err}
            target = None
            for e in trustlist.list_entries(self.router):
                if entry_id and e.get("ID") == entry_id:
                    target = e
                    break
            if target is None:
                return {"ok": False,
                        "error": "白名单里找不到这条记录（可能已被删除）"}
            try:
                res = trustlist.update(self.router, target["ID"], name,
                                       local_ip,
                                       None if port == "-1" else port, remote)
            except RouterError as e:
                return {"ok": False, "error": str(e)}
            if not trustlist.ok(res):
                return {"ok": False, "error": f"设备拒绝：{res}"}
            self.syncer.counters.bump(updated=1)
            self.syncer.counters.flush()
            self.syncer._log_event("updated", trigger="网页操作",
                                   device=name, entry=name, addr=local_ip,
                                   old_addr=target.get("LocalIp") or "",
                                   port=_port_label(port))
            return {"ok": True}
