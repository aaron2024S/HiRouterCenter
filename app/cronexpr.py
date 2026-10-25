# -*- coding: utf-8 -*-
"""受限 cron 表达式（5 段：分 时 日 月 周）—— 零依赖解析 + 人话描述。

为什么自己写而不用 croniter
--------------------------
本程序是**离线打包**（offline/ 下自带纯标准库源码），引入 croniter 意味着
离线包要多背一个第三方依赖、还要跟它的 Python 版本兼容性缠斗。而这里只
需要 5 段 cron 里最常用的一小块语法（``* , - /``），一百来行就够了。

支持与不支持
------------
支持：``*`` / 数字 / ``a-b`` 范围 / ``*/n`` 步进 / ``a-b/n`` / 逗号列表，
以及它们的组合（如 ``0,30 3-5/2 * * 1-5``）。
不支持：``@daily`` 之类的别名、年份段、L/W/# 等扩展 —— 用到直接报
「不支持」，绝不静默猜。

星期约定
--------
跟 crontab 一致：0 和 7 都表示周日，1=周一 … 6=周六。
内部的集合统一把 7 归并成 0（周日在前，与 Python ``tm_wday`` 对齐转换）。

日+周同时限制
-------------
采用 Vixie cron 的标准语义：日与周**都有**限制时是「或」的关系
（匹配其中之一就触发）；只有一个有限制时就按那个来。
"""
from __future__ import annotations

import time

# (字段中文名, 最小值, 最大值) —— 顺序即表达式顺序
_FIELDS = (("分钟", 0, 59), ("小时", 0, 23), ("日期", 1, 31),
           ("月份", 1, 12), ("星期", 0, 7))

_WEEKCN = {0: "日", 1: "一", 2: "二", 3: "三", 4: "四", 5: "五", 6: "六"}


def normalize(expr: str) -> str:
    """存储用：压掉多余空白。"""
    return " ".join(str(expr or "").split())


def _parse_field(text: str, name: str, lo: int, hi: int) -> frozenset[int]:
    """解析一段。任何看不懂/超范围的写法都抛 ValueError，消息给人看。"""
    text = text.strip()
    if not text:
        raise ValueError("%s这一段是空的" % name)
    out: set[int] = set()
    for part in text.split(","):
        part = part.strip()
        if not part:
            raise ValueError("%s里有多余的逗号" % name)
        step = 1
        rng: str
        if part.startswith("*/"):
            rng, step_s = "*", part[2:]
        elif "/" in part:
            rng, step_s = part.split("/", 1)
        else:
            rng, step_s = part, ""
        if step_s:
            if not step_s.isdigit() or int(step_s) < 1:
                raise ValueError("%s的步进要是正整数：%s" % (name, step_s))
            step = int(step_s)
        if rng == "*":
            a, b = lo, hi
        elif "-" in rng:
            aa, bb = rng.split("-", 1)
            if not (aa.strip().isdigit() and bb.strip().isdigit()):
                raise ValueError("%s的范围写法不对：%s" % (name, rng))
            a, b = int(aa), int(bb)
        else:
            if not rng.isdigit():
                raise ValueError("%s只能是数字或 *：%s" % (name, rng))
            a = b = int(rng)
        if not (lo <= a <= hi and lo <= b <= hi) or a > b:
            raise ValueError("%s超出范围（%d~%d）：%s" % (name, lo, hi, rng))
        out.update(range(a, b + 1, step))
    if not out:
        raise ValueError("%s没有选出任何值" % name)
    if name == "星期" and 7 in out:      # crontab：7 也是周日
        out.add(0)
        out.discard(7)
    return frozenset(out)


def parse(expr: str) -> tuple[frozenset[int], ...]:
    """解析成 5 个值集合（分钟 小时 日期 月份 星期，周日=0）。坏写法抛 ValueError。"""
    parts = normalize(expr).split(" ")
    if len(parts) != 5:
        raise ValueError(
            "cron 表达式要 5 段（分钟 小时 日期 月份 星期），用空格隔开，"
            "现在只有 %d 段" % len(parts))
    return tuple(_parse_field(p, _FIELDS[i][0], _FIELDS[i][1], _FIELDS[i][2])
                 for i, p in enumerate(parts))


def _matches_day(dom: frozenset[int], dow: frozenset[int],
                 lt: time.struct_time) -> bool:
    """Vixie 语义：两段都受限 → 或；否则按受限的那个。"""
    dom_full = len(dom) == 31
    dow_full = len(dow) == 7
    if dom_full and dow_full:
        return True
    on_dom = lt.tm_mday in dom
    on_dow = ((lt.tm_wday + 1) % 7) in dow
    if dom_full:
        return on_dow
    if dow_full:
        return on_dom
    return on_dom or on_dow


def match(expr: str, lt: time.struct_time) -> bool:
    """某个本地时间（精确到分）是否命中。"""
    f_min, f_hour, f_dom, f_mon, f_dow = parse(expr)
    return (lt.tm_min in f_min and lt.tm_hour in f_hour
            and lt.tm_mon in f_mon
            and _matches_day(f_dom, f_dow, lt))


def _day_start(ts: float) -> float:
    lt = time.localtime(ts)
    return time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, 0, 0, 0, 0, 0, -1))


def next_after(expr: str, ts: float, max_days: int = 800) -> float | None:
    """> ts 的最近一个触发点（本地时间，分钟粒度）。找不到返回 None。"""
    f_min, f_hour, f_dom, f_mon, f_dow = parse(expr)
    base = _day_start(ts)
    mins = sorted(f_min)
    for doff in range(0, max_days):
        day = base + doff * 86400.0
        lt = time.localtime(day)
        if lt.tm_mon not in f_mon:
            continue
        if not _matches_day(f_dom, f_dow, lt):
            continue
        for h in sorted(f_hour):
            for m in mins:
                st = time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday,
                                  h, m, 0, 0, 0, -1))
                if st > ts:
                    return st
    return None


def prev_within(expr: str, ts: float, lookback_min: int) -> float | None:
    """<= ts 的最近一个触发点，只往前找 lookback_min 分钟；没有返回 None。

    调度器判「到点」只需要往回看一个窗口（几分钟），判「已错过」
    才会传 8 天 —— 从当前分钟起逐分钟往回扫，最多一万来次，只在
    启动时跑一遍，开销可忽略。
    """
    start = ts - (ts % 60)                # 对齐到当前分钟
    for i in range(0, lookback_min + 1):
        st = start - i * 60
        if match(expr, time.localtime(st)):
            return st
    return None


def _span(vals: list[int]) -> str:
    """值集合 → 紧凑中文：连续段写「一~五」，散值用「、」。"""
    if not vals:
        return ""
    runs: list[tuple[int, int]] = []
    a = b = vals[0]
    for v in vals[1:]:
        if v == b + 1:
            b = v
        else:
            runs.append((a, b))
            a = b = v
    runs.append((a, b))
    parts = []
    for x, y in runs:
        parts.append(str(x) if x == y else "%d~%d" % (x, y))
    return "、".join(parts)


def _at(hh: int, mm: int) -> str:
    return "%02d:%02d" % (hh, mm)


def human(expr: str) -> str:
    """一句话人话，页面表格「重复」列和弹窗预览都用它。"""
    f_min, f_hour, f_dom, f_mon, f_dow = parse(expr)
    mins, hours = sorted(f_min), sorted(f_hour)
    mon_full = len(f_mon) == 12
    dom_full = len(f_dom) == 31
    dow_full = len(f_dow) == 7
    dom_one = len(f_dom) == 1
    m_one, h_one = len(mins) == 1, len(hours) == 1

    at = _at(hours[0], mins[0]) if (m_one and h_one) else ""
    # 前缀：不是每个月都跑
    prefix = "" if mon_full else "%s 月的 " % _span(sorted(f_mon))

    # 日期部分
    if dom_full and dow_full:
        day = "每天" if at else ""
    elif dom_full and sorted(f_dow) == [1, 2, 3, 4, 5]:
        day = "周一到周五"
    elif dom_full and len(f_dow) == 1:
        day = "每周" + _WEEKCN[next(iter(f_dow))]
    elif dom_full:
        day = "每周" + "、".join(_WEEKCN[d] for d in sorted(f_dow))
    elif dom_one and dow_full:
        d = next(iter(f_dom))
        day = "%d 日" % d if prefix else "每月 %d 日" % d
    elif dow_full:
        day = "%s 日" % _span(sorted(f_dom)) if prefix else "每月 %s 日" % _span(sorted(f_dom))
    else:
        day = ("每月 %s 日或每周 %s"
               % (_span(sorted(f_dom)),
                  "、".join(_WEEKCN[d] for d in sorted(f_dow))))

    # 时刻部分
    if at:
        when = (" " + at) if (day or prefix) else ""
    elif dom_full and dow_full and len(f_hour) == 24:
        # 只动了分钟：*/5 或 0,15,30,45 这类
        if len(mins) == 60:
            when = ""
        elif len(mins) > 1 and mins == list(range(mins[0], 60, mins[1] - mins[0])):
            when = " 每 %d 分钟" % (mins[1] - mins[0])
        elif m_one:
            when = " 每小时第 %d 分" % mins[0]
        else:
            when = " 第 %s 分" % _span(mins)
    elif len(f_hour) == 24:
        when = " 每小时第 %s 分" % _span(mins)
    else:
        hm = _span(hours) + " 点"
        if not m_one:
            hm += "第 %s 分" % _span(mins)
        else:
            hm += "%02d 分" % mins[0]
        when = " " + hm
    text = (prefix + day + when).strip()
    return text if text else "每分钟"
