# -*- coding: utf-8 -*-
"""计划任务：**什么时候执行在 NAS 上算，路由器只负责「现在做」**。

为什么不在路由器里排计划
------------------------
Q7 的「重启计划」「定时重拨」两个页面在 Web 端被固件裁掉了（`/more` 下 30 个
二级页面逐个确认过，没有它们；也没有通配路由兜底）。接口名还留在前端代码里，
但没有可用的字段定义 —— 凭空构造 body 只会拿到错误码。所以调度放在本地。

四条硬约束
----------
1. **先落盘再发送**。执行前先把 `last_slot` 写进 tasks.json 并 fsync，然后才发
   HTTP。哪怕发送瞬间容器被停掉，也不会因为「没留下记录」而重复触发。
2. **错过不补跑**。醒来时已经过了计划点超过 WINDOW 秒，只记一条「已错过」。
   否则 NAS 半夜启动会立刻重启一次路由器。
3. **执行后进入静默期**。重启/重拨会让本程序自己也连不上路由器，这段既不能算
   同步失败、也不能重试 —— 重试就是反复重启。
4. **停容器即不执行**。这是方案唯一的硬边界，页面上直接写明，不藏。

顺带说明「静默期」为什么按类型分档：重启 240 秒（固件重启 + 拨号 + Wi-Fi 起来）、
重拨 150 秒（前端自己等 11 秒再刷新，实测重拨就十来秒）、信道优化 60 秒
（Wi-Fi 要重开）、功率模式 20 秒（几乎无感）。
"""
from __future__ import annotations

import json
import logging
import os
import re
import threading
import time

log = logging.getLogger("ipv6sync.tasks")

KINDS = {
    "reboot": "重启路由器",
    "redial": "重新拨号",
    "wifi_power": "Wi-Fi 功率模式",
    "channel": "信道优化",
}

POWER_MODES = {0: "睡眠模式", 1: "一般模式", 2: "穿墙模式"}

WINDOW = 180.0          # 计划点之后多久之内还算「到点」
MAX_TASKS = 32          # 上限，防止误操作灌进来几百条

QUIET = {               # 执行后多久内不碰路由器、不判定同步失败
    "reboot": 240.0,
    "redial": 150.0,
    "wifi_power": 20.0,
    "channel": 60.0,
}

_WEEK = {1: "一", 2: "二", 3: "三", 4: "四", 5: "五", 6: "六", 7: "日"}


# --------------------------------------------------------------------------
# 时间计算（全部本地时区；中国无夏令时，按 86400 秒回退/前进是安全的）
# --------------------------------------------------------------------------

def parse_at(s: str):
    m = re.match(r"^(\d{1,2}):(\d{2})$", str(s or "").strip())
    if not m:
        raise ValueError("时间要写成 HH:MM，例如 04:30")
    h, mi = int(m.group(1)), int(m.group(2))
    if not (0 <= h <= 23 and 0 <= mi <= 59):
        raise ValueError("时间超出范围（00:00 ~ 23:59）")
    return h, mi


def _stamp_of_day(day_epoch: float, hh: int, mm: int) -> float:
    lt = time.localtime(day_epoch)
    return time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday,
                        hh, mm, 0, 0, 0, -1))


def _days_of(task: dict) -> list[int]:
    days = task.get("days") or []
    out = sorted({int(d) for d in days if 1 <= int(d) <= 7})
    return out or [1, 2, 3, 4, 5, 6, 7]


def last_slot(task: dict, now: float) -> float | None:
    """<= now 的最近一个计划点；没有则 None。往前看 8 天足够覆盖「每周一次」。"""
    try:
        hh, mm = parse_at(task.get("at"))
    except ValueError:
        return None
    days = _days_of(task)
    best = None
    for back in range(0, 8):
        day = now - back * 86400.0
        if (time.localtime(day).tm_wday + 1) not in days:
            continue
        st = _stamp_of_day(day, hh, mm)
        if st <= now and (best is None or st > best):
            best = st
    return best


def next_slot(task: dict, now: float) -> float | None:
    """> now 的最近一个计划点；永远有值（除非 at 非法）。"""
    try:
        hh, mm = parse_at(task.get("at"))
    except ValueError:
        return None
    days = _days_of(task)
    for fwd in range(0, 9):
        day = now + fwd * 86400.0
        if (time.localtime(day).tm_wday + 1) not in days:
            continue
        st = _stamp_of_day(day, hh, mm)
        if st > now:
            return st
    return None


def due_slot(task: dict, now: float, window: float = WINDOW) -> float | None:
    """这一刻该不该执行；该执行则返回计划点时间戳。

    三个条件缺一不可：最近计划点在窗口内、这个计划点还没执行过、任务已启用。
    """
    if not task.get("enabled", True):
        return None
    slot = last_slot(task, now)
    if slot is None or (now - slot) > window:
        return None
    # 计划生效之前的点根本不存在 —— 14:00 新建的「每天 10:00」任务，
    # 今天 10:00 那次不应该被当成到点，更不该立刻执行。
    if slot <= float(task.get("since") or 0):
        return None
    if float(task.get("last_slot") or 0) >= slot:
        return None
    return slot


# --------------------------------------------------------------------------
# 任务模型
# --------------------------------------------------------------------------

def tasks_path(settings_file: str) -> str:
    """与 settings.json / state.json 同目录（默认 /data/tasks.json）。"""
    d = os.path.dirname(os.path.abspath(settings_file or "/data/settings.json"))
    return os.path.join(d, "tasks.json")


def _new_id(now: float | None = None) -> str:
    base = int((now or time.time()) * 1000)
    return "t%x" % base


def clean_task(raw: dict, now: float | None = None) -> dict:
    """校验并规范化一条任务。坏值一律抛 ValueError，不静默兜底。"""
    if not isinstance(raw, dict):
        raise ValueError("任务格式不对")
    kind = str(raw.get("kind") or "").strip()
    if kind not in KINDS:
        raise ValueError("任务类型不对，可选：" + " / ".join(KINDS.values()))

    name = str(raw.get("name") or "").strip() or KINDS[kind]
    if len(name) > 30:
        raise ValueError("任务名最多 30 个字")

    hh, mm = parse_at(raw.get("at"))
    days = _days_of(raw)
    params: dict = {}
    if kind == "wifi_power":
        pm = raw.get("params", {}).get("power_mode")
        try:
            pm = int(pm)
        except (TypeError, ValueError):
            raise ValueError("Wi-Fi 功率模式要选 睡眠模式 / 一般模式 / 穿墙模式 之一")
        if pm not in POWER_MODES:
            raise ValueError("功率模式只能选上面三档之一")
        params["power_mode"] = pm

    out = {
        "id": str(raw.get("id") or "").strip() or _new_id(now),
        "name": name,
        "kind": kind,
        "enabled": bool(raw.get("enabled", True)),
        "at": "%02d:%02d" % (hh, mm),
        "days": days,
        "params": params,
    }
    # 运行时字段原样保留（编辑时不清空执行历史）
    for k in ("last_slot", "last_run_at", "last_ok", "last_msg"):
        if k in raw:
            out[k] = raw[k]
    # 计划生效时刻：早于它的计划点不算「到点」，也不算「已错过」。
    # 旧文件里没有这个字段 → 0，行为与以前一致。
    try:
        out["since"] = float(raw.get("since") or 0)
    except (TypeError, ValueError):
        out["since"] = 0.0
    return out


def describe(task: dict) -> str:
    """一句话说清什么时候执行，页面直接显示。"""
    at = task.get("at") or "--:--"
    days = _days_of(task)
    if days == [1, 2, 3, 4, 5, 6, 7]:
        when = "每天 " + at
    elif len(days) == 1:
        when = "每周%s " % _WEEK[days[0]] + at
    else:
        when = "每周" + "、".join(_WEEK[d] for d in days) + " " + at
    if task.get("kind") == "wifi_power":
        when += " → " + POWER_MODES.get(
            (task.get("params") or {}).get("power_mode"), "?")
    return when


# --------------------------------------------------------------------------
# 执行：把「现在做」翻成路由器上那四个按钮
# --------------------------------------------------------------------------

_ID_RE = re.compile(r"^Internet[A-Za-z0-9_.\-]*\d+$")
_WANISH = re.compile(r"internet|wan", re.I)
_DETAIL_MAX = 12


def _scan(obj, depth: int, out: list) -> None:
    """深度优先收集「键名 → 非空字符串值」，键名只保留直接父级那个。"""
    if depth > 6:
        return
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, str) and v.strip():
                out.append((k, v.strip()))
            else:
                _scan(v, depth + 1, out)
    elif isinstance(obj, list):
        for v in obj:
            _scan(v, depth + 1, out)


def find_wan_id(obj) -> str:
    """从 GET wan 的返回里挖出活动连接的 ID。

    固件前端取的是 `wanTypeActivecontrol.ID`，但**真机上既不是
    `InternetConnection_N`、也不一定叫 ID**（2026-10-24 报「读不到当前 WAN
    连接 ID」就是这么来的），所以不再赌格式，而是按「这个字段有多像连接标识」
    打分取最高的：

      100  键名 Path，值里带 WAN / Internet（请求体本身就收 `Path`，最像）
       90  键名 Path
       80  键名 ID / Id / id，值里带 WAN / Internet
       70  键名 ID / Id / id
       60  值本身形如 InternetConnection_1 / …WANPPPConnection.1

    同分取先出现的（深度优先，活动连接一般排在前面）。
    """
    pairs: list = []
    _scan(obj, 0, pairs)
    best, top = "", 0
    for k, v in pairs:
        if k == "Path":
            s = 100 if _WANISH.search(v) else 90
        elif k in ("ID", "Id", "id"):
            s = 80 if _WANISH.search(v) else 70
        elif _ID_RE.match(v):
            s = 60
        else:
            continue
        if s > top:
            best, top = v, s
    return best


def wan_keys(obj) -> list:
    """诊断用：wan 响应的顶层键（不带值），定位「读不到连接 ID」到底缺什么。"""
    if isinstance(obj, dict):
        return [str(k) for k in obj.keys()][:_DETAIL_MAX]
    if isinstance(obj, list):
        return ["[列表 %d 项]" % len(obj)]
    return [type(obj).__name__]


def set_power_mode(router, mode: int) -> dict:
    """切 Wi-Fi 功率模式。

    2026-10-24 在真机上验证过（浏览器登录态，走页面自己的请求层）：

      · `GET wlanradio` 只返回 7 个字段，**不含 SSID、不含 Wi-Fi 密码**：
        Enable2G / Enable5G / InitEnable2G / InitEnable5G / PowerMode /
        PowerModeChgTip / WLANMode
      · 最小写 `{"PowerMode": 2}` 之后回读，7 个字段一个没丢一个没空
      · PowerMode 1 → 2 真实生效，回读 = 2，再写回 1 也成功

    所以这里**先试最小写**（绝不上整包）；最小写没生效才退回「拿到的 7 字段
    原样带上、只改 PowerMode」再写一次，并回读校验。
    """
    info = router.get("wlanradio")
    cur = info.get("PowerMode") if isinstance(info, dict) else None
    try:
        cur = int(cur)
    except (TypeError, ValueError):
        cur = None
    if cur == mode:
        return {"ok": True, "skipped": True,
                "msg": "当前已经是「%s」，无需改动" % POWER_MODES[mode]}

    router.post("wlanradio", {"PowerMode": mode})          # 最小写
    back = router.get("wlanradio")
    if isinstance(back, dict) and int(back.get("PowerMode", -1)) == mode:
        return {"ok": True, "msg": "已切到「%s」" % POWER_MODES[mode]}

    if isinstance(info, dict):                              # 退回完整 7 字段
        full = dict(info)
        full["PowerMode"] = mode
        router.post("wlanradio", full)
        back = router.get("wlanradio")
        if isinstance(back, dict) and int(back.get("PowerMode", -1)) == mode:
            # 「整字段写回」是内部实现细节，只进日志，不显示给用户
            log.info("功率模式最小写没生效，已用完整字段写回成功")
            return {"ok": True, "msg": "已切到「%s」" % POWER_MODES[mode]}

    got = back.get("PowerMode") if isinstance(back, dict) else None
    try:
        got = int(got)
    except (TypeError, ValueError):
        got = None
    tail = ("当前仍是「%s」" % POWER_MODES[got]) if got in POWER_MODES else "档位没有变化"
    return {"ok": False, "msg": "切换没生效，" + tail}


def optimize_channel(router) -> dict:
    """一键优化信道。

    固件里这个按钮发的是 `{action:"UpdateAll", ChannelDeploy:<当前值>,
    NetChannelMode:<当前值>}` —— **其余字段原样带上**，不是写死。所以先读
    一次拿当前值，取不到才退回默认。
    """
    info = router.get("channelinfo")
    data = {"action": "UpdateAll"}
    if isinstance(info, dict):
        for k in ("ChannelDeploy", "NetChannelMode"):
            if k in info:
                data[k] = info[k]
    router.post("channelinfo", data)
    return {"ok": True, "msg": "已发起一键优化信道"}


def apply(router, task: dict) -> dict:
    """执行一条任务。返回 {"ok": bool, "msg": str}，不抛业务异常。"""
    kind = task.get("kind")
    if kind == "reboot":
        # 固件前端发的就是 data 为空的重启请求；这里连 data 键都不带
        router.post("service/reboot.cgi", {}, wrapped=False)
        return {"ok": True, "msg": "已发出重启指令，路由器约 1 分钟后断开、2~3 分钟恢复"}
    if kind == "redial":
        wan = router.get("wan")
        path = find_wan_id(wan)
        if not path:
            # 拿到的字段名只写日志（排错用），界面上不出现任何内部参数
            log.warning("读不到 WAN 连接 ID，wan 返回的字段：%s",
                        "、".join(wan_keys(wan)) or "空")
            return {"ok": False, "msg": "读不到当前的宽带连接，无法重拨"}
        router.post("wan", {"Path": path}, action="reconnect")
        log.info("重新拨号：Path=%s", path)
        return {"ok": True, "msg": "已发起重新拨号，十来秒后恢复"}
    if kind == "wifi_power":
        return set_power_mode(router, int((task.get("params") or {})["power_mode"]))
    if kind == "channel":
        return optimize_channel(router)
    return {"ok": False, "msg": "未知任务类型"}


def user_facing_error(exc: BaseException) -> str:
    """把内部异常翻成一句人话。

    界面上「上次结果」列和右下角弹窗显示的都是这里返回的句子 ——
    **不出现接口路径、字段名、异常类名、原始响应**，那些只进容器日志。
    """
    name = type(exc).__name__
    if name in ("NotLoggedIn", "SessionExpired"):
        return "路由器登录已失效，请到「同步与设置」里重新登录路由器"
    if name == "RouterError":
        return "路由器没有按预期回应，请稍后重试"
    return "执行出错，请稍后重试"


# --------------------------------------------------------------------------
# 调度器
# --------------------------------------------------------------------------

class Tasks:
    """任务集合 + 到点判定 + 执行 + 静默期。

    `get_router` 是 callable 而不是 router 实例 —— 网页里改了路由器密码会重建
    router，调度器必须每次现取，否则永远用着旧会话。

    `guard` 是一把外部互斥（Node 传的是 syncer.lock）。**必须传**：CSRF 令牌
    每次响应都轮换，两个线程同时往路由器发请求会互相把 token 覆盖掉，轻则
    请求失败、重则会话被注销。所以任务执行必须和同步轮次串行。
    """

    def __init__(self, get_router, path: str, guard=None, clock=None):
        self._get_router = get_router
        self.path = path
        if guard is None:
            import contextlib
            self._guard = contextlib.nullcontext
        else:
            self._guard = guard
        # 只用来给「计划生效时刻」（since）打时间戳；测试注入固定时钟，
        # 生产里就是 time.time。
        self._clock = clock or time.time
        self._lock = threading.RLock()
        self._items: list[dict] = []
        self._quiet_until = 0.0
        self._running = ""          # 正在执行的任务 id
        with self._lock:
            self._load()

    # ---------- 落盘 ----------

    def _load(self):
        try:
            with open(self.path, encoding="utf-8") as f:
                raw = json.load(f)
        except (OSError, ValueError):
            return
        if not isinstance(raw, dict):
            return
        items = raw.get("tasks")
        if isinstance(items, list):
            for v in items:
                try:
                    self._items.append(clean_task(v))
                except ValueError:
                    continue                       # 坏条目跳过，不影响其余的
        try:
            self._quiet_until = float(raw.get("quiet_until") or 0)
        except (TypeError, ValueError):
            self._quiet_until = 0.0

    def _save_locked(self):
        d = os.path.dirname(self.path)
        if d:
            os.makedirs(d, exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"tasks": self._items, "quiet_until": self._quiet_until},
                      f, ensure_ascii=False, indent=1)
            f.flush()
            os.fsync(f.fileno())          # 掉电也不丢：先落盘，再发送
        os.replace(tmp, self.path)

    def save(self):
        with self._lock:
            self._save_locked()

    # ---------- 视图 ----------

    def view(self) -> dict:
        now = time.time()
        with self._lock:
            rows = []
            for t in self._items:
                row = dict(t)
                row["when"] = describe(t)
                row["kind_label"] = KINDS.get(t["kind"], t["kind"])
                nxt = next_slot(t, now)
                row["next_at"] = (time.strftime("%m-%d %H:%M",
                                                time.localtime(nxt)) if nxt else "")
                row["running"] = (t["id"] == self._running)
                rows.append(row)
            quiet = max(0, int(self._quiet_until - now))
            return {"ok": True, "tasks": rows,
                    "now": time.strftime("%Y-%m-%d %H:%M:%S"),
                    # 计划按容器本地时间算；把时区一并吐出来，用户一眼能看出
                    # 「容器跑的是 UTC 还是 +0800」，不用去翻 compose
                    "tz": "%s (%s)" % (time.strftime("%Z") or "UTC",
                                       time.strftime("%z") or "+0000"),
                    "utc": time.strftime("%z") in ("+0000", "-0000"),
                    "quiet_left": quiet,
                    "window": int(WINDOW),
                    "kinds": KINDS, "power_modes": POWER_MODES}

    # ---------- 增删改 ----------

    def upsert(self, raw: dict) -> dict:
        task = clean_task(raw)
        stamp = self._clock()
        with self._lock:
            for i, t in enumerate(self._items):
                if t["id"] == task["id"]:
                    # 改了执行时间/星期/类型 = 计划重新开始，从这一刻起算；
                    # 只改名字或启停则保留原来的生效时刻。
                    resched = ((t.get("at"), t.get("days") or [], t.get("kind"))
                               != (task.get("at"), task.get("days") or [],
                                   task.get("kind")))
                    task["since"] = stamp if resched else float(t.get("since") or 0.0)
                    self._items[i] = task
                    self._save_locked()
                    return {"ok": True, "task": task}
            if len(self._items) >= MAX_TASKS:
                raise ValueError("最多 %d 个任务" % MAX_TASKS)
            # 新建：计划从这一刻起才存在。否则「14:00 建的每天 10:00 任务」
            # 会被回头判定为今天 10:00「已错过」——那是任务还没出生时的点。
            task["since"] = stamp
            self._items.append(task)
            self._save_locked()
        return {"ok": True, "task": task}

    def delete(self, tid: str) -> dict:
        with self._lock:
            n = len(self._items)
            self._items = [t for t in self._items if t["id"] != tid]
            if len(self._items) == n:
                raise ValueError("没有这个任务")
            self._save_locked()
        return {"ok": True}

    def toggle(self, tid: str, enabled: bool) -> dict:
        with self._lock:
            for t in self._items:
                if t["id"] == tid:
                    was = bool(t.get("enabled", True))
                    t["enabled"] = bool(enabled)
                    if enabled and not was:
                        # 重新启用时重新计时：停用期间没跑是应该的，
                        # 不能起来就报一串「已错过」。
                        t["since"] = self._clock()
                    self._save_locked()
                    return {"ok": True, "enabled": t["enabled"]}
        raise ValueError("没有这个任务")

    # ---------- 静默期 ----------

    def quiet_left(self) -> float:
        return max(0.0, self._quiet_until - time.time())

    def _set_quiet(self, seconds: float):
        with self._lock:
            self._quiet_until = max(self._quiet_until, time.time() + seconds)
            self._save_locked()

    # ---------- 执行 ----------

    def run(self, tid: str, manual: bool = False) -> dict:
        """执行一条任务。手动触发不受时间窗口限制，但仍会进静默期。"""
        with self._lock:
            task = next((t for t in self._items if t["id"] == tid), None)
            if task is None:
                raise ValueError("没有这个任务")
            if self._running:
                return {"ok": False, "error": "另一个任务正在执行，请稍后"}
            if manual and self.quiet_left() > 0:
                return {"ok": False,
                        "error": "路由器刚执行过动作，%d 秒后再试" % int(self.quiet_left())}
            self._running = tid
            # 标记「已触发」并**先落盘**，再发 HTTP
            task["last_slot"] = float(task.get("last_slot") or 0)
            if manual:
                task["last_run_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
            task["last_ok"] = None
            task["last_msg"] = "执行中…"
            self._save_locked()

        try:
            with self._guard():
                res = apply(self._get_router(), task)
        except Exception as e:                       # noqa: BLE001
            # 完整堆栈进日志；界面上只给一句人话（不含任何内部参数）
            log.exception("计划任务「%s」执行出错", task["name"])
            res = {"ok": False, "msg": user_facing_error(e)}

        with self._lock:
            task["last_ok"] = bool(res.get("ok"))
            task["last_msg"] = str(res.get("msg") or "")
            self._running = ""
            self._save_locked()
        if res.get("ok"):
            # 手动执行也要进静默期：否则用户点完「立即重启」，下一轮同步立刻
            # 连不上路由器，就会一路累计失败次数、甚至推送告警。
            self._set_quiet(QUIET.get(task["kind"], 60.0))
            log.info("计划任务「%s」执行成功：%s", task["name"], res.get("msg"))
        else:
            log.warning("计划任务「%s」执行失败：%s", task["name"], res.get("msg"))
        return {"ok": bool(res.get("ok")), "msg": str(res.get("msg") or ""),
                "task": dict(task)}

    def tick(self, now: float | None = None) -> dict | None:
        """调度心跳（每 3 秒一次）。到点就执行，绝不重试。"""
        now = now or time.time()
        if self._running or self.quiet_left() > 0:
            return None

        with self._lock:
            pending = [(due_slot(t, now), t) for t in self._items]
            pending = [(s, t) for s, t in pending if s is not None]
            if not pending:
                return None
            pending.sort(key=lambda x: (x[0], x[1]["name"]))
            slot, task = pending[0]
            # 同一时刻只跑一个：其余的直接记「已跳过」，否则每一轮心跳都会重新
            # 判定成到点，把日志刷满。
            for s, other in pending[1:]:
                other["last_slot"] = s
                other["last_run_at"] = time.strftime(
                    "%Y-%m-%d %H:%M:%S", time.localtime(s))
                other["last_ok"] = True
                other["last_msg"] = "同一时刻已有任务在执行，本次跳过"
                log.info("计划任务「%s」与「%s」同时到点，跳过前者",
                         other["name"], task["name"])
            if float(task.get("last_slot") or 0) >= slot:
                return None
            task["last_slot"] = slot                 # 先标记
            task["last_run_at"] = time.strftime(
                "%Y-%m-%d %H:%M:%S", time.localtime(slot))
            task["last_ok"] = None
            task["last_msg"] = "执行中…"
            self._save_locked()                      # **先落盘**
            tid = task["id"]

        res = self.run(tid)
        return res

    # ---------- 边界扫描（什么时候说明白） ----------

    def mark_missed(self, now: float | None = None) -> list[str]:
        """启动时把「早就过了窗口、又没执行过」的计划点标成已错过。

        不补跑 —— 补跑意味着 NAS 半夜重启后立刻重启一次路由器。
        """
        now = now or time.time()
        out = []
        with self._lock:
            for t in self._items:
                if not t.get("enabled", True):
                    continue
                slot = last_slot(t, now)
                if slot is None or (now - slot) <= WINDOW:
                    continue
                # 任务当时还不存在（或刚改过计划）—— 那个点不是「错过」，
                # 是根本没安排。14:00 新建的「每天 10:00」就属于这种。
                if slot <= float(t.get("since") or 0):
                    continue
                if float(t.get("last_slot") or 0) >= slot:
                    continue
                t["last_slot"] = slot
                t["last_run_at"] = time.strftime(
                    "%Y-%m-%d %H:%M:%S", time.localtime(slot))
                t["last_ok"] = True
                t["last_msg"] = "已错过（容器当时没在运行）"
                out.append(t["name"])
            if out:
                self._save_locked()
        for n in out:
            log.warning("计划任务「%s」的计划点已错过 —— 不补跑", n)
        return out
