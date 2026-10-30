# -*- coding: utf-8 -*-
"""设备卡三个动作（改名 / 限速 / 黑名单）与新增字段的单测。

接口与 payload 全部逆向自固件前端（终端页 chunk）：
    改名   POST system/changedevicename {action:"update", data:[{ActualName, ID}]}
    限速   POST app/qosclass_host        （整条 HostInfo 回传，只改三个字段）
    黑名单 POST ntwk/wlanfilterenhance   （整份 2.4G/5G 配置，W/B 名单一起改）
"""
import threading
import unittest

from app import node as nd
from app.node import Node
from app.router import RouterError


class FakeSyncer:
    """只提供锁 + 登录态，不碰真路由器。"""

    def __init__(self):
        self.lock = threading.RLock()

    def ensure_login(self):
        return True

    def login_backoff_remaining(self):
        return 0

    @property
    def last_error(self):
        return ""


class FakeRouter:
    def __init__(self, hosts=None, wl=None):
        self.hosts = hosts if hosts is not None else []
        self.wl = wl if wl is not None else [
            {"MACAddressControlEnabled": True, "WMACAddresses": [], "BMACAddresses": []},
            {"MACAddressControlEnabled": True, "WMACAddresses": [], "BMACAddresses": []},
        ]
        self.posts = []

    def get(self, name, params=None):
        if name == "HostInfo":
            return self.hosts
        if name == "ntwk/wlanfilterenhance":
            return self.wl
        if name == "device/topology":
            return []
        raise AssertionError("假路由器没实现 GET " + name)

    def post(self, name, data=None, wrapped=True, action=None):
        self.posts.append({"name": name, "data": data, "action": action})
        return {}


def make_node(router):
    n = Node.__new__(Node)
    n.router = router
    n.syncer = FakeSyncer()
    return n


HOST = {
    "ID": 7, "MACAddress": "AA:BB:CC:DD:EE:01", "IPAddress": "192.168.3.20",
    "InterfaceType": "5GHz", "DevBrands": "huawei", "ActualManu": "Default",
    "ActualName": "旧名字", "HostName": "host-01", "Active": 1,
    "AccessRecord": "2026-10-30 15:00:00", "DownRate": 820, "UpRate": 66,
    "DeviceDownRateEnable": 0, "DeviceMaxUpLoadRate": 0, "DeviceMaxDownLoadRate": 0,
    # 累计收发（单位 KB）。固件前端不用这两个字段，但真机确实返回，离线也不清零
    "RxKBytes": 73400320, "TxKBytes": 7340032,
}


class HostRowFields(unittest.TestCase):
    def test_rows_carry_new_fields(self):
        n = make_node(FakeRouter(hosts=[dict(HOST)]))
        n.cfg = type("C", (), {"state_file": ""})()
        rows = n._host_rows()
        self.assertEqual(len(rows), 1)
        r = rows[0]
        self.assertEqual(r["id"], 7)
        self.assertEqual(r["iface"], "5GHz")
        self.assertEqual(r["brand"], "huawei")
        self.assertEqual(r["down_kb"], 820)
        self.assertEqual(r["up_kb"], 66)
        self.assertIsInstance(r["online_secs"], int)

    def test_cumulative_bytes_kept_for_offline_host(self):
        """累计收发是「累计量」，设备下线不清零 —— 离线行也要带上，不能跟着 active 归零。"""
        off = dict(HOST, Active=0, OfflineRecord="2026-10-30 10:00:00",
                   RxKBytes=1200000, TxKBytes=5000)
        n = make_node(FakeRouter(hosts=[off]))
        n.cfg = type("C", (), {"state_file": ""})()
        r = n._host_rows()[0]
        self.assertFalse(r["active"])
        self.assertEqual(r["rx_kb"], 1200000)
        self.assertEqual(r["tx_kb"], 5000)
        self.assertEqual(r["down_kb"], 0)          # 实时速率离线归零，和累计是两回事

    def test_cumulative_bytes_tolerate_garbage(self):
        bad = dict(HOST, RxKBytes="", TxKBytes=None)
        n = make_node(FakeRouter(hosts=[bad]))
        n.cfg = type("C", (), {"state_file": ""})()
        r = n._host_rows()[0]
        self.assertEqual(r["rx_kb"], 0)
        self.assertEqual(r["tx_kb"], 0)

    def test_limit_fields_follow_master_switch(self):
        # 总开关关着：即使字段里残留数字，界面上也应该显示「不限速」
        n = make_node(FakeRouter(hosts=[dict(HOST)]))
        n.cfg = type("C", (), {"state_file": ""})()
        self.assertEqual(n._host_rows()[0]["limit_up"], 0)
        self.assertEqual(n._host_rows()[0]["limit_down"], 0)
        h = dict(HOST, DeviceDownRateEnable=1,
                 DeviceMaxUpLoadRate=5120, DeviceMaxDownLoadRate=20480)
        n = make_node(FakeRouter(hosts=[h]))
        n.cfg = type("C", (), {"state_file": ""})()
        r = n._host_rows()[0]
        self.assertEqual(r["limit_up"], 5120)
        self.assertEqual(r["limit_down"], 20480)

    def test_manual_brand_wins(self):
        h = dict(HOST, ActualManu="xiaomi")
        n = make_node(FakeRouter(hosts=[h]))
        n.cfg = type("C", (), {"state_file": ""})()
        self.assertEqual(n._host_rows()[0]["brand"], "xiaomi")

    def test_offline_has_no_rates_or_secs(self):
        h = dict(HOST, Active=0, OfflineRecord="2026-10-29 10:00:00")
        n = make_node(FakeRouter(hosts=[h]))
        n.cfg = type("C", (), {"state_file": ""})()
        r = n._host_rows()[0]
        self.assertFalse(r["active"])
        self.assertIsNone(r["online_secs"])
        self.assertEqual(r["down_kb"], 0)
        self.assertEqual(r["up_kb"], 0)

    def test_access_record_unparsable_is_none(self):
        self.assertIsNone(nd._online_secs({"AccessRecord": "not-a-date"}))


class Rename(unittest.TestCase):
    def test_posts_changedevicename_with_id(self):
        r = FakeRouter(hosts=[dict(HOST)])
        res = make_node(r).rename_host("aa:bb:cc:dd:ee:01", "  客厅电视  ")
        self.assertTrue(res["ok"])
        p = r.posts[-1]
        self.assertEqual(p["name"], "system/changedevicename")
        self.assertEqual(p["action"], "update")
        self.assertEqual(p["data"], [{"ActualName": "客厅电视", "ID": 7}])

    def test_empty_name_rejected(self):
        with self.assertRaises(Exception):
            make_node(FakeRouter(hosts=[dict(HOST)])).rename_host(HOST["MACAddress"], "   ")

    def test_too_long_name_rejected(self):
        with self.assertRaises(Exception):
            make_node(FakeRouter(hosts=[dict(HOST)])).rename_host(HOST["MACAddress"], "x" * 21)

    def test_unknown_mac_reports_friendly_error(self):
        # 找不到设备属于「用户输入/状态」问题：抛 SettingsError，由 webui 转成 400 + 人话
        with self.assertRaises(Exception) as ctx:
            make_node(FakeRouter(hosts=[dict(HOST)])).rename_host("11:22:33:44:55:66", "x")
        self.assertIn("找不到这台设备", str(ctx.exception))


class Limit(unittest.TestCase):
    def test_sets_three_fields_and_posts_host_object(self):
        r = FakeRouter(hosts=[dict(HOST)])
        res = make_node(r).set_host_limit(HOST["MACAddress"], 2048, 10240)
        self.assertTrue(res["ok"])
        p = r.posts[-1]
        self.assertEqual(p["name"], "app/qosclass_host")
        self.assertEqual(p["data"]["DeviceMaxUpLoadRate"], 2048)
        self.assertEqual(p["data"]["DeviceMaxDownLoadRate"], 10240)
        self.assertEqual(p["data"]["DeviceDownRateEnable"], 1)
        self.assertEqual(p["data"]["MACAddress"], HOST["MACAddress"])

    def test_zero_clears_limit(self):
        r = FakeRouter(hosts=[dict(HOST, DeviceDownRateEnable=1,
                                   DeviceMaxUpLoadRate=2048,
                                   DeviceMaxDownLoadRate=10240)])
        make_node(r).set_host_limit(HOST["MACAddress"], 0, 0)
        d = r.posts[-1]["data"]
        self.assertEqual(d["DeviceDownRateEnable"], 0)
        self.assertEqual(d["DeviceMaxDownLoadRate"], 0)

    def test_string_numbers_accepted(self):
        r = FakeRouter(hosts=[dict(HOST)])
        res = make_node(r).set_host_limit(HOST["MACAddress"], "1024", "2048")
        self.assertTrue(res["ok"])
        self.assertEqual(r.posts[-1]["data"]["DeviceMaxDownLoadRate"], 2048)

    def test_garbage_rejected(self):
        with self.assertRaises(Exception):
            make_node(FakeRouter(hosts=[dict(HOST)])).set_host_limit(HOST["MACAddress"], "abc", 1)


class Blacklist(unittest.TestCase):
    def test_add_puts_mac_into_both_bands_blacklist(self):
        r = FakeRouter(hosts=[dict(HOST)])
        res = make_node(r).set_host_blacklist(HOST["MACAddress"], True)
        self.assertTrue(res["ok"])
        p = r.posts[-1]
        self.assertEqual(p["name"], "ntwk/wlanfilterenhance")
        for band in p["data"]:
            macs = [e["MACAddress"] for e in band["BMACAddresses"]]
            self.assertIn(HOST["MACAddress"], macs)
            self.assertNotIn(HOST["MACAddress"],
                             [e["MACAddress"] for e in band["WMACAddresses"]])

    def test_remove_puts_mac_back_to_whitelist(self):
        r = FakeRouter(hosts=[dict(HOST)])
        n = make_node(r)
        n.set_host_blacklist(HOST["MACAddress"], True)
        n.set_host_blacklist(HOST["MACAddress"], False)
        for band in r.posts[-1]["data"]:
            self.assertNotIn(HOST["MACAddress"],
                             [e["MACAddress"] for e in band["BMACAddresses"]])
            self.assertIn(HOST["MACAddress"],
                          [e["MACAddress"] for e in band["WMACAddresses"]])

    def test_idempotent_add(self):
        r = FakeRouter(hosts=[dict(HOST)])
        n = make_node(r)
        n.set_host_blacklist(HOST["MACAddress"], True)
        n.set_host_blacklist(HOST["MACAddress"], True)
        band = r.posts[-1]["data"][0]
        self.assertEqual(len([e for e in band["BMACAddresses"]
                              if e["MACAddress"] == HOST["MACAddress"]]), 1)

    def test_requires_master_switch(self):
        wl = [{"MACAddressControlEnabled": False, "WMACAddresses": [], "BMACAddresses": []}]
        res = make_node(FakeRouter(hosts=[dict(HOST)], wl=wl)).set_host_blacklist(
            HOST["MACAddress"], True)
        self.assertFalse(res["ok"])
        self.assertIn("总开关", res["error"])

    def test_capacity_limited(self):
        full = [{"MACAddress": "00:00:00:00:00:%02X" % i, "HostName": ""} for i in range(32)]
        wl = [{"MACAddressControlEnabled": True, "WMACAddresses": [], "BMACAddresses": list(full)},
              {"MACAddressControlEnabled": True, "WMACAddresses": [], "BMACAddresses": list(full)}]
        res = make_node(FakeRouter(hosts=[dict(HOST)], wl=wl)).set_host_blacklist(
            HOST["MACAddress"], True)
        self.assertFalse(res["ok"])
        self.assertIn("满", res["error"])


if __name__ == "__main__":
    unittest.main()
