# -*- coding: utf-8 -*-
"""受限 cron 解析器 + 计划任务 cron 档（每小时/每月/自定义）。"""
import re
import time
import unittest

from app import cronexpr as ce
from app import tasks as tk


def _ts(y, mo, d, h, mi, s=0):
    """固定本地时间戳（分钟粒度，秒清零的由调用方保证）。"""
    return time.mktime((y, mo, d, h, mi, s, 0, 0, -1))


class TestCronParse(unittest.TestCase):
    def test_valid_shapes(self):
        for expr in ("30 * * * *", "0 3 * * *", "*/5 * * * *", "0,15 2 * * 1-5",
                     "30 4 1 * *", "0 22 * * 0", "0 22 * * 7", "5-10/2 6-8 * * 1,3"):
            ce.parse(expr)                       # 不抛即合法

    def test_wrong_field_count(self):
        for expr in ("", "0 3 * *", "* * * * * *", "0 3"):
            with self.assertRaises(ValueError):
                ce.parse(expr)

    def test_range_rejected(self):
        for expr in ("60 * * * *", "0 24 * * *", "0 3 32 * *", "0 3 * 13 *",
                     "0 3 * * 8", "0 3 * * -1"):
            with self.assertRaises(ValueError):
                ce.parse(expr)

    def test_garbage_rejected(self):
        for expr in ("a * * * *", "*/0 * * * *", "1-3-5 * * * *",
                     "0 3 * * *;", "0, 3 * * *"):
            with self.assertRaises(ValueError):
                ce.parse(expr)

    def test_dow_7_is_sunday(self):
        self.assertEqual(ce.parse("0 3 * * 7")[4], ce.parse("0 3 * * 0")[4])

    def test_normalize_collapses_spaces(self):
        self.assertEqual(ce.normalize("  0   3   *  *  1-5 "), "0 3 * * 1-5")


class TestCronNextPrev(unittest.TestCase):
    NOW = _ts(2026, 10, 25, 10, 15)          # 周日 10:15

    def test_next_hourly(self):
        nxt = ce.next_after("30 * * * *", self.NOW)
        self.assertEqual(time.strftime("%H:%M", time.localtime(nxt)), "10:30")

    def test_next_daily_skips_today_if_past(self):
        nxt = ce.next_after("0 3 * * *", self.NOW)
        self.assertEqual(time.strftime("%m-%d %H:%M", time.localtime(nxt)), "10-26 03:00")

    def test_next_monthly_crosses_month(self):
        nxt = ce.next_after("30 4 1 * *", self.NOW)
        self.assertEqual(time.strftime("%m-%d %H:%M", time.localtime(nxt)), "11-01 04:30")

    def test_next_weekdays_from_sunday(self):
        nxt = ce.next_after("0 3 * * 1-5", self.NOW)   # 周日 → 周一
        self.assertEqual(time.strftime("%m-%d %H:%M", time.localtime(nxt)), "10-26 03:00")

    def test_next_dom_and_dow_is_or(self):
        nxt = ce.next_after("0 3 1 * 1", self.NOW)     # 每月1日 或 周一
        self.assertEqual(time.strftime("%m-%d %H:%M", time.localtime(nxt)), "10-26 03:00")

    def test_prev_within_small_window(self):
        now = _ts(2026, 10, 25, 9, 31, 30)             # 09:30 过 90 秒
        got = ce.prev_within("30 * * * *", now, 4)
        self.assertEqual(time.strftime("%H:%M", time.localtime(got)), "09:30")

    def test_prev_within_none_when_far(self):
        got = ce.prev_within("0 3 * * *", self.NOW, 4)
        self.assertIsNone(got)

    def test_prev_within_long_lookback(self):
        got = ce.prev_within("0 3 * * *", self.NOW, 8 * 1440)
        self.assertEqual(time.strftime("%m-%d %H:%M", time.localtime(got)), "10-25 03:00")


class TestCronHuman(unittest.TestCase):
    def test_common_shapes(self):
        self.assertEqual(ce.human("0 3 * * *"), "每天 03:00")
        self.assertEqual(ce.human("0 3 * * 1-5"), "周一到周五 03:00")
        self.assertEqual(ce.human("30 4 1 * *"), "每月 1 日 04:30")
        self.assertEqual(ce.human("30 * * * *"), "每小时第 30 分")
        self.assertEqual(ce.human("*/5 * * * *"), "每 5 分钟")
        self.assertEqual(ce.human("0 4 * * 1,3,5"), "每周一、三、五 04:00")
        self.assertEqual(ce.human("30 8 1,15 * *"), "每月 1、15 日 08:30")
        self.assertEqual(ce.human("15 2 1,15 3 *"), "3 月的 1、15 日 02:15")

    def test_every_minute(self):
        self.assertEqual(ce.human("* * * * *"), "每分钟")


class TestTaskCronModel(unittest.TestCase):
    def test_clean_task_stores_cron(self):
        t = tk.clean_task({"kind": "reboot", "cron": " 30  4 1 * * "})
        self.assertEqual(t["cron"], "30 4 1 * *")
        self.assertNotIn("at", t)
        self.assertNotIn("days", t)

    def test_clean_task_rejects_bad_cron(self):
        with self.assertRaises(ValueError):
            tk.clean_task({"kind": "reboot", "cron": "0 3 * *"})

    def test_clean_task_keeps_at_days_for_old_format(self):
        t = tk.clean_task({"kind": "reboot", "at": "04:30"})
        self.assertEqual(t["at"], "04:30")
        self.assertEqual(t["days"], [1, 2, 3, 4, 5, 6, 7])
        self.assertNotIn("cron", t)

    def test_describe_cron(self):
        self.assertEqual(tk.describe({"kind": "reboot", "cron": "30 4 1 * *"}),
                         "每月 1 日 04:30")

    def test_describe_old_format_unchanged(self):
        self.assertEqual(tk.describe({"kind": "reboot", "at": "04:30",
                                      "days": [1, 2, 3, 4, 5, 6, 7]}), "每天 04:30")

    def test_next_slot_cron(self):
        t = {"kind": "reboot", "cron": "30 * * * *"}
        now = _ts(2026, 10, 25, 10, 15)
        self.assertEqual(time.strftime("%H:%M", time.localtime(tk.next_slot(t, now))),
                         "10:30")

    def test_last_slot_cron_window(self):
        t = {"kind": "reboot", "cron": "30 * * * *"}
        now = _ts(2026, 10, 25, 10, 32, 30)
        got = tk.last_slot(t, now, lookback_min=4)
        self.assertEqual(time.strftime("%H:%M", time.localtime(got)), "10:30")

    def test_due_slot_fires_and_marks_once(self):
        t = {"kind": "wake", "cron": "*/5 * * * *", "enabled": True,
             "since": 0.0, "last_slot": 0.0, "params": {"devices": []}}
        # 注意 wake 任务不需要真设备列表也行？——不行，clean_task 会校验；
        # 这里绕过 clean_task 直接测 due_slot 的纯时间逻辑。
        now = _ts(2026, 10, 25, 10, 6, 30)             # 10:05 过 90 秒
        slot = tk.due_slot(t, now)
        self.assertIsNotNone(slot)
        self.assertEqual(time.strftime("%H:%M", time.localtime(slot)), "10:05")
        t["last_slot"] = slot
        self.assertIsNone(tk.due_slot(t, now))         # 执行过就不再触发

    def test_due_slot_ignores_old_monthly_point(self):
        # 每月 1 日的点早就过了窗口 —— due_slot 不该往回扫 8 天也算到点
        t = {"kind": "wake", "cron": "0 3 1 * *", "enabled": True,
             "since": 0.0, "last_slot": 0.0}
        now = _ts(2026, 10, 25, 10, 0)
        self.assertIsNone(tk.due_slot(t, now))


class TestTaskCronScheduler(unittest.TestCase):
    def setUp(self):
        import os
        import tempfile
        self.dir = tempfile.mkdtemp(prefix="hrc-cron-")
        self.path = os.path.join(self.dir, "tasks.json")
        self.tasks = tk.Tasks(lambda: None, self.path, clock=lambda: _ts(2026, 10, 25, 10, 0))

    def _wake(self, cron):
        return {"kind": "wake", "name": "夜唤", "cron": cron,
                "params": {"devices": [{"mac": "AA:BB:CC:DD:EE:FF",
                                        "name": "测试机", "ipv4": "192.168.3.9"}]}}

    def test_upsert_cron_and_describe(self):
        r = self.tasks.upsert(self._wake("30 * * * *"))
        self.assertEqual(r["task"]["cron"], "30 * * * *")
        view = self.tasks.view()
        self.assertTrue(view["tasks"][0]["when"].startswith("每小时第 30 分"))
        self.assertTrue(re.match(r"^\d{2}-\d{2} \d{2}:\d{2}$", view["tasks"][0]["next_at"]))

    def test_edit_cron_reschedules(self):
        r = self.tasks.upsert(self._wake("30 * * * *"))
        before = r["task"]["since"]
        r2 = self.tasks.upsert(dict(self._wake("0 3 * * *"),
                                    id=r["task"]["id"]))
        self.assertEqual(r2["task"]["cron"], "0 3 * * *")
        self.assertGreaterEqual(r2["task"]["since"], before)

    def test_tick_fires_cron_task(self):
        self.tasks.upsert(self._wake("*/5 * * * *"))
        # 10:05:30 —— 计划点 10:05 在窗口内
        res = self.tasks.tick(_ts(2026, 10, 25, 10, 5, 30))
        self.assertIsNotNone(res)
        self.assertTrue(res["ok"])

    def test_mark_missed_cron(self):
        r = self.tasks.upsert(self._wake("0 3 * * *"))
        tid = r["task"]["id"]
        self.tasks._items[0]["since"] = 0.0
        missed = self.tasks.mark_missed(_ts(2026, 10, 25, 10, 0))
        self.assertIn("夜唤", missed)
        self.assertEqual(self.tasks._items[0]["last_msg"], "已错过（容器当时没在运行）")
        _ = tid


if __name__ == "__main__":
    unittest.main()
