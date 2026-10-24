# -*- coding: utf-8 -*-
"""通知模块离线测试：渠道预设 / 请求渲染 / 事件模型 / 投递策略 / 同步联动。

全程不联网：HTTP 打桩在 notify._post，SMTP 只测参数校验。
"""
import json
import os
import sys
import tempfile
import time
import unittest
import urllib.parse
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import discover, notify, notify_events as ne, notify_presets as P  # noqa: E402
from app.config import Config, Rule  # noqa: E402
from app.sync import Syncer  # noqa: E402

# 复用 test_logic 的假路由器。两种导入布局都要兼容：
#   本地 `python -m unittest discover -s tests`  → tests/ 在 sys.path，顶层导入
#   镜像内 `discover -s tests -t .`              → 只有项目根在 sys.path，走包路径
try:
    from test_logic import FakeRouter
except ImportError:  # noqa: E203
    from tests.test_logic import FakeRouter  # type: ignore

NAS_MAC = "00:11:22:AA:BB:CC"
OLD_ADDR = "240e:3a4:48ff:6d10:7173:1ffc:64ed:82c0"

CTX = {
    "title": "设备已离线",
    "text": "客厅摄像头 已离线",
    "level": "normal",
    "event": "dev_offline",
    "time": "2026-10-24 18:00:00",
    "panel": "http://192.168.3.1:6600",
}


def make_cfg(**kw) -> Config:
    cfg = Config(
        host="192.168.3.1", username="admin", password="x",
        session_file=None, poll_interval=1,
        rules=[Rule(name="NAS", port=None, remote_ip="::/0", mac=None)],
    )
    for k, v in kw.items():
        setattr(cfg, k, v)
    return cfg


def wecom_on(**kw) -> Config:
    """老格式（三开关）建配置 —— 顺便验证迁移路径。"""
    kw.setdefault("notify_wecom_id", "85d3153d-1a2b")
    return make_cfg(notify_wecom_enabled=True, **kw)


# --------------------------------------------------------------------------
# 渠道预设：字段定义与请求渲染
# --------------------------------------------------------------------------

class PresetSpecTest(unittest.TestCase):
    def test_eleven_channels_exposed(self):
        types = [s["t"] for s in P.specs()]
        self.assertEqual(len(types), 11)
        for t in ("wecom", "telegram", "bark", "ntfy", "gotify", "dingtalk",
                  "feishu", "serverchan", "pushplus", "smtp", "webhook"):
            self.assertIn(t, types)

    def test_every_preset_has_label_and_fields(self):
        for spec in P.specs():
            self.assertTrue(spec["l"], spec["t"])
            self.assertTrue(spec["f"], spec["t"])
            for f in spec["f"]:
                self.assertIn("k", f)
                self.assertIn("l", f)

    def test_required_fields_detected(self):
        self.assertEqual(P.missing_fields("gotify", {}), ["服务器", "应用令牌"])
        self.assertEqual(P.missing_fields("wecom", {"key": "k"}), [])

    def test_unknown_type_rejected(self):
        with self.assertRaises(ValueError):
            P.build_request("nope", {}, CTX)


class PresetRenderTest(unittest.TestCase):
    def test_json_body_escapes_quotes_and_newlines(self):
        """坑 1：正文里的引号 / 换行不转义就是非法 JSON。"""
        ctx = dict(CTX, text='他说"你好"\n第二行\\反斜杠')
        req = P.build_request("gotify", {"server": "https://p.example.com",
                                         "token": "tk"}, ctx)
        payload = json.loads(req["data"].decode("utf-8"))   # 不能抛
        self.assertIn('"你好"', payload["message"])
        self.assertIn("\n", payload["message"])

    def test_server_not_percent_encoded(self):
        """坑 2：整串 https:// 被编码连协议头都解析不出来。"""
        req = P.build_request("bark", {"server": "https://api.day.app",
                                       "key": "k1"}, CTX)
        self.assertEqual(req["url"], "https://api.day.app/k1")

    def test_telegram_token_keeps_colon(self):
        req = P.build_request("telegram", {"token": "123:ABC", "chatId": "-1"},
                              CTX)
        self.assertIn("/bot123:ABC/sendMessage", req["url"])

    def test_wecom_payload_and_mention(self):
        req = P.build_request("wecom", {"key": "k-1", "mentioned": "138,139"},
                              CTX)
        self.assertIn("key=k-1", req["url"])
        payload = json.loads(req["data"].decode("utf-8"))
        self.assertEqual(payload["msgtype"], "text")
        self.assertIn("设备已离线", payload["text"]["content"])
        self.assertEqual(payload["text"]["mentioned_mobile_list"],
                         ["138", "139"])

    def test_ntfy_raw_text_body(self):
        req = P.build_request("ntfy", {"topic": "t1", "token": "tk_x"}, CTX)
        self.assertEqual(req["url"], "https://ntfy.sh/t1")
        self.assertIn("设备已离线".encode(), req["data"])
        self.assertEqual(req["headers"]["Authorization"], "Bearer tk_x")

    def test_serverchan_form_encoded(self):
        req = P.build_request("serverchan", {"sendkey": "SCT1"}, CTX)
        form = urllib.parse.parse_qs(req["data"].decode("utf-8"))
        self.assertEqual(form["title"], ["设备已离线"])

    def test_dingtalk_sign_only_encoded_once(self):
        """坑 3：签名的 base64 只能 percent 编码一次（%3D 不能变 %253D）。"""
        req = P.build_request("dingtalk", {"token": "tok", "secret": "SECabc"},
                              CTX, ts=1700000000)
        q = urllib.parse.parse_qs(urllib.parse.urlparse(req["url"]).query)
        self.assertEqual(q["timestamp"], ["1700000000"])
        sign = q["sign"][0]
        self.assertNotIn("%", sign, "签名被二次编码了")
        self.assertTrue(sign.endswith("="), "base64 结尾的 = 应当还在")

    def test_dingtalk_sign_value_is_hmac_of_secret(self):
        import base64
        import hashlib
        import hmac
        req = P.build_request("dingtalk", {"token": "t", "secret": "SEC"},
                              CTX, ts=1700000000)
        q = urllib.parse.parse_qs(urllib.parse.urlparse(req["url"]).query)
        want = base64.b64encode(hmac.new(b"SEC", b"1700000000\nSEC",
                                         hashlib.sha256).digest()).decode()
        self.assertEqual(q["sign"][0], want)

    def test_feishu_sign_goes_into_body(self):
        req = P.build_request("feishu", {"token": "abc", "secret": "s1"},
                              CTX, ts=1700000000)
        payload = json.loads(req["data"].decode("utf-8"))
        self.assertEqual(payload["timestamp"], "1700000000")
        self.assertTrue(payload["sign"])
        self.assertIn("设备已离线", payload["content"]["text"])

    def test_no_secret_means_no_sign_params(self):
        req = P.build_request("dingtalk", {"token": "t"}, CTX, ts=1)
        self.assertEqual(req["url"],
                         "https://oapi.dingtalk.com/robot/send?access_token=t")

    def test_webhook_custom_headers_and_body(self):
        req = P.build_request("webhook", {
            "url": "https://e.com/hook", "method": "put",
            "contentType": "application/json",
            "headers": '{"X-Event":"{{event}}"}',
            "body": '{"t":"{{title}}","x":"{{text}}","lv":"{{level}}"}',
        }, CTX)
        self.assertEqual(req["method"], "PUT")
        self.assertEqual(req["headers"]["X-Event"], "dev_offline")
        payload = json.loads(req["data"].decode("utf-8"))
        self.assertEqual(payload["t"], "设备已离线")
        self.assertEqual(payload["lv"], "normal")

    def test_webhook_bad_header_json(self):
        with self.assertRaises(ValueError):
            P.build_request("webhook", {"url": "https://e.com",
                                        "headers": "not json"}, CTX)

    def test_unknown_placeholder_left_alone(self):
        """用户正文里有花括号不能被吃掉，也不能抛异常。"""
        req = P.build_request("gotify", {"server": "https://p", "token": "t"},
                              dict(CTX, text="值 {foo}"))
        self.assertIn("{foo}", json.loads(req["data"])["message"])


class ResponseCheckTest(unittest.TestCase):
    def test_wecom_errcode(self):
        self.assertEqual(P.check_response("wecom", '{"errcode":0}'), "")
        self.assertIn("93000",
                      P.check_response("wecom", '{"errcode":93000,"errmsg":"x"}'))

    def test_telegram_ok_false(self):
        self.assertIn("chat not found", P.check_response(
            "telegram", '{"ok":false,"description":"chat not found"}'))
        self.assertEqual(P.check_response("telegram", '{"ok":true}'), "")

    def test_feishu_and_pushplus_codes(self):
        self.assertEqual(P.check_response("feishu", '{"code":0}'), "")
        self.assertIn("19001", P.check_response(
            "feishu", '{"code":19001,"msg":"sign match fail"}'))
        self.assertEqual(P.check_response("pushplus", '{"code":200}'), "")
        self.assertIn("903", P.check_response(
            "pushplus", '{"code":903,"msg":"无效的用户token"}'))

    def test_non_json_body_ignored(self):
        self.assertEqual(P.check_response("wecom", "not json"), "")


# --------------------------------------------------------------------------
# 渠道配置：校验 / 迁移
# --------------------------------------------------------------------------

class ChannelConfigTest(unittest.TestCase):
    def test_bad_type_rejected(self):
        with self.assertRaises(ValueError):
            notify.normalize_channel({"type": "sms"})

    def test_empty_values_dropped(self):
        c = notify.normalize_channel({"type": "ntfy", "name": "n",
                                      "config": {"topic": "t", "token": ""}})
        self.assertNotIn("token", c["config"])
        self.assertEqual(c["config"]["topic"], "t")

    def test_wecom_full_url_trimmed_to_key(self):
        c = notify.normalize_channel({"type": "wecom", "config": {
            "key": "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=abc-1"}})
        self.assertEqual(c["config"]["key"], "abc-1")

    def test_feishu_url_trimmed_to_token(self):
        c = notify.normalize_channel({"type": "feishu", "config": {
            "token": "https://open.feishu.cn/open-apis/bot/v2/hook/xyz"}})
        self.assertEqual(c["config"]["token"], "xyz")

    def test_defaults_filled(self):
        c = notify.normalize_channel({"type": "bark", "config": {"key": "k"}})
        self.assertEqual(c["config"]["server"], "https://api.day.app")
        c = notify.normalize_channel({"type": "ntfy", "config": {"topic": "t"}})
        self.assertEqual(c["config"]["server"], "https://ntfy.sh")

    def test_legacy_migration(self):
        cfg = make_cfg(notify_ntfy_enabled=True,
                       notify_ntfy_url="https://ntfy.sh/mytopic",
                       notify_ntfy_token="tk",
                       notify_wecom_enabled=True, notify_wecom_id="k-1",
                       notify_gotify_enabled=False, notify_gotify_url="")
        chans = notify.channels(cfg)
        by = {c["type"]: c for c in chans}
        self.assertEqual(set(by), {"ntfy", "wecom"})
        self.assertEqual(by["ntfy"]["config"]["server"], "https://ntfy.sh")
        self.assertEqual(by["ntfy"]["config"]["topic"], "mytopic")
        self.assertTrue(by["wecom"]["enabled"])

    def test_new_format_wins_over_legacy(self):
        cfg = make_cfg(notify_wecom_enabled=True, notify_wecom_id="old")
        cfg.notify_channels = [{"id": "a1", "type": "bark", "name": "b",
                                "enabled": True, "config": {"key": "k"}}]
        self.assertEqual([c["type"] for c in notify.channels(cfg)], ["bark"])

    def test_save_rejects_bad_list(self):
        cfg = make_cfg()
        with self.assertRaises(ValueError):
            notify.save(cfg, "nope")
        with self.assertRaises(ValueError):
            notify.save(cfg, [{"type": "unknown-type"}])

    def test_save_assigns_unique_ids(self):
        cfg = make_cfg()
        got = notify.save(cfg, [{"type": "ntfy", "config": {"topic": "a"}},
                                {"type": "ntfy", "config": {"topic": "b"}}])
        self.assertEqual(len(got), 2)
        self.assertNotEqual(got[0]["id"], got[1]["id"])


# --------------------------------------------------------------------------
# 投递：多渠道路由与容错
# --------------------------------------------------------------------------

class DeliverTest(unittest.TestCase):
    def test_no_channel_is_noop(self):
        self.assertEqual(notify.send_all(make_cfg(), CTX), [])

    def test_all_three_push_together(self):
        cfg = make_cfg(notify_ntfy_enabled=True, notify_ntfy_url="https://n/t",
                       notify_wecom_enabled=True, notify_wecom_id="k",
                       notify_gotify_enabled=True,
                       notify_gotify_url="https://g", notify_gotify_token="t")
        with mock.patch.object(notify, "_post", return_value=(True, "{}")):
            res = notify.send_all(cfg, CTX)
        self.assertEqual([r["type"] for r in res], ["ntfy", "gotify", "wecom"])
        self.assertTrue(all(r["ok"] for r in res))

    def test_business_error_marked_failed(self):
        cfg = make_cfg(notify_wecom_enabled=True, notify_wecom_id="k")
        with mock.patch.object(notify, "_post",
                               return_value=(True, '{"errcode":93000}')):
            res = notify.send_all(cfg, CTX)
        self.assertFalse(res[0]["ok"])
        self.assertIn("93000", res[0]["error"])

    def test_http_failure_keeps_peer_working(self):
        cfg = make_cfg(notify_ntfy_enabled=True, notify_ntfy_url="https://n/t",
                       notify_wecom_enabled=True, notify_wecom_id="k")

        def fake_post(url, data, headers, method="POST"):
            if "qyapi" in url:
                return False, "connection refused"
            return True, ""
        with mock.patch.object(notify, "_post", side_effect=fake_post):
            res = notify.send_all(cfg, CTX)
        by = {r["type"]: r for r in res}
        self.assertTrue(by["ntfy"]["ok"])
        self.assertFalse(by["wecom"]["ok"])

    def test_exception_never_escapes(self):
        cfg = make_cfg(notify_wecom_enabled=True, notify_wecom_id="k")
        with mock.patch.object(notify, "_post",
                               side_effect=RuntimeError("boom")):
            res = notify.send_all(cfg, CTX)
        self.assertFalse(res[0]["ok"])
        self.assertIn("boom", res[0]["error"])

    def test_incomplete_channel_reported_not_sent(self):
        cfg = make_cfg()
        cfg.notify_channels = [{"id": "x", "type": "gotify", "name": "g",
                                "enabled": True, "config": {"server": ""}}]
        with mock.patch.object(notify, "_post") as p:
            res = notify.send_all(cfg, CTX)
        p.assert_not_called()
        self.assertFalse(res[0]["ok"])
        self.assertIn("配置不全", res[0]["error"])

    def test_disabled_channel_skipped(self):
        cfg = make_cfg()
        cfg.notify_channels = [{"id": "x", "type": "ntfy", "name": "n",
                                "enabled": False,
                                "config": {"server": "https://n", "topic": "t"}}]
        self.assertEqual(notify.send_all(cfg, CTX), [])

    def test_smtp_missing_fields(self):
        cfg = make_cfg()
        cfg.notify_channels = [{"id": "m", "type": "smtp", "name": "mail",
                                "enabled": True,
                                "config": {"host": "smtp.qq.com"}}]
        res = notify.send_all(cfg, CTX)
        self.assertFalse(res[0]["ok"])
        self.assertIn("配置不全", res[0]["error"])


# --------------------------------------------------------------------------
# 事件模型：表 / 静默时段 / 去重 / 历史
# --------------------------------------------------------------------------

class EventTableTest(unittest.TestCase):
    def test_fourteen_events(self):
        self.assertEqual(len(ne.EVENTS), 14)
        codes = [e[0] for e in ne.EVENTS]
        self.assertEqual(len(codes), len(set(codes)), "事件代码不能重复")

    def test_kid_window_event_removed(self):
        """「儿童上网时段已调整」根本感知不到，必须不在表里。"""
        for code, _g, title, _lv, _d in ne.EVENTS:
            self.assertNotIn("儿童", title)

    def test_titles_are_short(self):
        for code, _g, title, _lv, _d in ne.EVENTS:
            self.assertLessEqual(len(title), 14, f"{code} 标题太长：{title}")

    def test_defaults_and_override(self):
        cfg = make_cfg()
        self.assertTrue(ne.event_enabled(cfg, "fw_add"))
        self.assertFalse(ne.event_enabled(cfg, "dev_new"))
        cfg.notify_events = {"dev_new": True, "fw_add": False}
        self.assertTrue(ne.event_enabled(cfg, "dev_new"))
        self.assertFalse(ne.event_enabled(cfg, "fw_add"))

    def test_unknown_code_ignored(self):
        self.assertEqual(ne.normalize_events({"nope": True, "fw_add": False}),
                         {"fw_add": False})

    def test_table_flags_reflect_config(self):
        cfg = make_cfg(notify_events={"fw_add": False})
        by = {e["code"]: e for e in ne.events_table(cfg)}
        self.assertFalse(by["fw_add"]["on"])
        self.assertTrue(by["fw_add"]["default"])


class QuietHoursTest(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(ne.parse_quiet("23:00-07:00"), (1380, 420))
        self.assertIsNone(ne.parse_quiet(""))
        self.assertIsNone(ne.parse_quiet("乱写"))

    def _at(self, hh, mm):
        t = time.localtime()
        return time.mktime((t.tm_year, t.tm_mon, t.tm_mday, hh, mm, 0, 0, 0, -1))

    def test_cross_midnight(self):
        self.assertTrue(ne.in_quiet("23:00-07:00", self._at(1, 30)))
        self.assertTrue(ne.in_quiet("23:00-07:00", self._at(23, 30)))
        self.assertFalse(ne.in_quiet("23:00-07:00", self._at(12, 0)))

    def test_same_day(self):
        self.assertTrue(ne.in_quiet("12:00-14:00", self._at(13, 0)))
        self.assertFalse(ne.in_quiet("12:00-14:00", self._at(15, 0)))

    def test_normalize(self):
        self.assertEqual(ne.normalize_quiet("23：00-7:00"), "23:00-07:00")
        self.assertEqual(ne.normalize_quiet(""), "")
        with self.assertRaises(ValueError):
            ne.normalize_quiet("晚上")

    def test_urgent_bypasses_quiet(self):
        cfg = make_cfg(notify_quiet="00:00-23:59",
                       notify_wecom_enabled=True, notify_wecom_id="k")
        with mock.patch.object(notify, "_post", return_value=(True, "")) as p:
            ne.dispatch(cfg, "fw_update", "普通事件")      # 被静默
            ne.dispatch(cfg, "fw_fail", "紧急事件")        # 照发
        self.assertEqual(p.call_count, 1)
        self.assertIn("紧急".encode(), p.call_args[0][1])


class DedupeTest(unittest.TestCase):
    def setUp(self):
        ne.reset_dedupe()
        self.cfg = make_cfg(notify_wecom_enabled=True, notify_wecom_id="k",
                            notify_dedupe=300)

    def tearDown(self):
        ne.reset_dedupe()

    def test_same_subject_suppressed(self):
        with mock.patch.object(notify, "_post", return_value=(True, "")) as p:
            ne.dispatch(self.cfg, "dev_offline", "a", subject="客厅摄像头")
            ne.dispatch(self.cfg, "dev_offline", "a", subject="客厅摄像头")
            ne.dispatch(self.cfg, "dev_offline", "b", subject="卧室电视")
        self.assertEqual(p.call_count, 2)

    def test_zero_window_disables(self):
        self.cfg.notify_dedupe = 0
        with mock.patch.object(notify, "_post", return_value=(True, "")) as p:
            ne.dispatch(self.cfg, "dev_offline", "a", subject="x")
            ne.dispatch(self.cfg, "dev_offline", "a", subject="x")
        self.assertEqual(p.call_count, 2)


class DispatchGateTest(unittest.TestCase):
    def test_master_switch_off(self):
        cfg = make_cfg(notify_enabled=False, notify_wecom_enabled=True,
                       notify_wecom_id="k")
        with mock.patch.object(notify, "_post") as p:
            self.assertEqual(ne.dispatch(cfg, "fw_add", "x"), [])
        p.assert_not_called()

    def test_event_off(self):
        cfg = make_cfg(notify_wecom_enabled=True, notify_wecom_id="k",
                       notify_events={"fw_add": False})
        with mock.patch.object(notify, "_post") as p:
            self.assertEqual(ne.dispatch(cfg, "fw_add", "x"), [])
        p.assert_not_called()

    def test_force_overrides_everything(self):
        cfg = make_cfg(notify_enabled=False, notify_quiet="00:00-23:59",
                       notify_wecom_enabled=True, notify_wecom_id="k")
        with mock.patch.object(notify, "_post", return_value=(True, "")) as p:
            ne.dispatch(cfg, "fw_add", "x", force=True)
        self.assertEqual(p.call_count, 1)

    def test_title_comes_from_event(self):
        cfg = make_cfg(notify_wecom_enabled=True, notify_wecom_id="k")
        with mock.patch.object(notify, "_post", return_value=(True, "")) as p:
            ne.dispatch(cfg, "dev_online", "NAS 上线了", subject="nas")
        payload = json.loads(p.call_args[0][1].decode("utf-8"))
        self.assertTrue(payload["text"]["content"].startswith("设备已上线"))


class HistoryTest(unittest.TestCase):
    def setUp(self):
        ne.reset_dedupe()
        self.tmp = tempfile.TemporaryDirectory()
        self.cfg = make_cfg(state_file=os.path.join(self.tmp.name, "state.json"),
                            notify_wecom_enabled=True, notify_wecom_id="k",
                            notify_history_max=50, notify_dedupe=0)

    def tearDown(self):
        ne.reset_dedupe()
        self.tmp.cleanup()

    def test_records_one_row_per_channel(self):
        with mock.patch.object(notify, "_post", return_value=(True, "")):
            ne.dispatch(self.cfg, "fw_add", "NAS 已加入白名单")
        rows = ne.read_history(self.cfg)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["title"], "已加入 IPv6 白名单")
        self.assertTrue(rows[0]["ok"])
        self.assertIn("NAS", rows[0]["text"])

    def test_failure_recorded(self):
        with mock.patch.object(notify, "_post", return_value=(False, "nope")):
            ne.dispatch(self.cfg, "fw_add", "x")
        rows = ne.read_history(self.cfg)
        self.assertFalse(rows[0]["ok"])
        self.assertEqual(rows[0]["error"], "nope")

    def test_trim_to_max(self):
        self.cfg.notify_history_max = 10
        with mock.patch.object(notify, "_post", return_value=(True, "")):
            for i in range(15):
                ne.dispatch(self.cfg, "fw_add", f"第 {i} 条")
        rows = ne.read_history(self.cfg)
        self.assertEqual(len(rows), 10)
        self.assertIn("第 14 条", rows[-1]["text"])

    def test_clear(self):
        with mock.patch.object(notify, "_post", return_value=(True, "")):
            ne.dispatch(self.cfg, "fw_add", "x")
        ne.clear_history(self.cfg)
        self.assertEqual(ne.read_history(self.cfg), [])

    def test_max_clamped(self):
        self.cfg.notify_history_max = 9999
        self.assertEqual(ne.history_max(self.cfg), 200)
        self.cfg.notify_history_max = 1
        self.assertEqual(ne.history_max(self.cfg), 10)

    def test_path_next_to_state_file(self):
        p = ne.history_path(os.path.join("X:" + os.sep, "data", "state.json"))
        self.assertEqual(os.path.basename(p), "notify.jsonl")


# --------------------------------------------------------------------------
# 与同步循环的联动
# --------------------------------------------------------------------------

class _LocalNetStub:
    def setUp(self):
        self._net_saved = (discover.local_candidates, discover.temporary_set)
        discover.local_candidates = lambda: [discover.canon(OLD_ADDR)]
        discover.temporary_set = lambda: set()

    def tearDown(self):
        discover.local_candidates, discover.temporary_set = self._net_saved


class SyncNotifyIntegrationTest(_LocalNetStub, unittest.TestCase):
    """白名单真有写入才发通知；没写入 / 演练模式 / 关掉事件都不发。"""

    def setUp(self):
        super().setUp()
        ne.reset_dedupe()
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        ne.reset_dedupe()
        self.tmp.cleanup()
        super().tearDown()

    def _cfg(self, **kw):
        kw.setdefault("state_file",
                      os.path.join(self.tmp.name, "state.json"))
        kw.setdefault("notify_wecom_id", "85d3153d-1a2b")
        kw.setdefault("notify_wecom_enabled", True)
        return make_cfg(**kw)

    def _tick(self, cfg):
        s = Syncer(cfg, FakeRouter(entries=[]))
        with mock.patch.object(notify, "send_all",
                               return_value=[{"id": "1", "name": "企业微信",
                                              "type": "wecom", "ok": True,
                                              "error": ""}]) as p:
            s.tick()
        return p

    def test_notify_sent_on_writes(self):
        p = self._tick(self._cfg())
        self.assertEqual(p.call_count, 1)
        ctx = p.call_args[0][1]
        self.assertEqual(ctx["title"], "已加入 IPv6 白名单")
        self.assertIn("NAS", ctx["text"])
        self.assertIn(OLD_ADDR, ctx["text"])

    def test_event_title_not_user_title(self):
        """标题由事件决定：老配置里的自定义标题不再影响推送。"""
        cfg = self._cfg(notify_title="家庭 NAS 上线提醒")
        p = self._tick(cfg)
        self.assertNotEqual(p.call_args[0][1]["title"], "家庭 NAS 上线提醒")

    def test_no_notify_when_unchanged(self):
        cfg = self._cfg()
        entries = [{"Name": "NAS", "LocalIp": OLD_ADDR,
                    "RemoteIp": "::/0", "Port": -1, "ID": "id1"}]
        s = Syncer(cfg, FakeRouter(entries=entries))
        with mock.patch.object(notify, "send_all", return_value=[]) as p:
            s.tick()
        p.assert_not_called()

    def test_no_notify_when_no_channel(self):
        s = Syncer(self._cfg(), FakeRouter(entries=[]))
        with mock.patch.object(notify, "send_all", return_value=[]) as p:
            snap = s.tick()
        self.assertEqual(p.call_count, 1)
        self.assertTrue(snap["ok"])

    def test_no_notify_in_dry_run(self):
        p = self._tick(self._cfg(dry_run=True))
        p.assert_not_called()

    def test_event_disabled_suppresses(self):
        cfg = self._cfg(notify_events={"fw_add": False, "fw_update": False})
        p = self._tick(cfg)
        p.assert_not_called()

    def test_notify_failure_never_breaks_tick(self):
        cfg = self._cfg()
        s = Syncer(cfg, FakeRouter(entries=[]))
        with mock.patch.object(notify, "send_all",
                               side_effect=RuntimeError("boom")):
            snap = s.tick()          # 不能抛
        self.assertTrue(snap["ok"])

    def test_device_baseline_round_sends_nothing(self):
        """第一轮只建基线：不能把「所有设备同时上线」糊一脸。"""
        s = Syncer(self._cfg(), FakeRouter(entries=[]))
        self.assertIsNone(s._dev_state)
        s._track_devices({})
        self.assertEqual(s._dev_state, {})       # 基线建好了，没发通知


if __name__ == "__main__":
    unittest.main()
