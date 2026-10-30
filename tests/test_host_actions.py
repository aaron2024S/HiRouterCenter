# -*- coding: utf-8 -*-
"""设备卡三个动作（改名 / 限速 / 黑名单）与新增字段的单测。

接口与 payload 全部逆向自固件前端（终端页 chunk）：
    改名   POST system/changedevicename {action:"update", data:[{ActualName, ID}]}
    限速   POST app/qosclass_host        （整条 HostInfo 回传，只改三个字段）
    黑名单 POST ntwk/wlanfilterenhance   （{"config2g":{…},"config5g":{…}}，
                                          名单字段是 WMacFilters / BMacFilters）
"""
import copy
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
    """按真机固件的脾气来的假路由器。

    关键点：`ntwk/wlanfilterenhance` 的写入**只认**
    `{"config2g": {...}, "config5g": {...}}` + `WMacFilters` / `BMacFilters`；
    形状不对（比如把 GET 那个数组原样丢回去）它会回一个成功响应但什么都不做。
    这正是 1.2.6 里「加入 / 移出黑名单点了没反应」的根因，所以这里必须照实模拟，
    否则测试只能证明代码自己自洽，证明不了对固件有效。
    """

    def __init__(self, hosts=None, wl=None, capacity=256, apply_writes=True):
        self.hosts = hosts if hosts is not None else []
        self.wl = wl if wl is not None else [
            {"MACAddressControlEnabled": True, "FrequencyBand": "2.4GHz",
             "WMACAddresses": [], "BMACAddresses": []},
            {"MACAddressControlEnabled": True, "FrequencyBand": "5GHz",
             "WMACAddresses": [], "BMACAddresses": []},
        ]
        self.capacity = capacity
        self.apply_writes = apply_writes   # False = 模拟「回成功但不照做」的固件
        self.posts = []

    def get(self, name, params=None):
        if name == "HostInfo":
            return self.hosts
        if name == "ntwk/wlanfilterenhance":
            # 每次读都是一份新 JSON，改动只能在 post 之后从 self.wl 里看到
            return copy.deepcopy(self.wl)
        if name == "deviceinfo":
            return {"MacFilterCapacity": self.capacity} if self.capacity else {}
        if name == "device/topology":
            return []
        raise AssertionError("假路由器没实现 GET " + name)

    def post(self, name, data=None, wrapped=True, action=None):
        self.posts.append({"name": name, "data": data, "action": action})
        if name == "ntwk/wlanfilterenhance" and self.apply_writes:
            self._apply_filter(data)
        return {}

    def _apply_filter(self, data):
        """像真固件一样解释写入体：只认 config2g/config5g + *Filters。"""
        if not isinstance(data, dict):
            return
        for idx, band in enumerate(self.wl):
            cfg = data.get("config2g" if idx == 0 else "config5g")
            if not isinstance(cfg, dict):
                continue
            for src, dst in (("WMacFilters", "WMACAddresses"),
                             ("BMacFilters", "BMACAddresses")):
                if src in cfg:
                    band[dst] = cfg[src]


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

    def test_sub_router_rename(self):
        """子路由也能改名 —— 手机 App 里能改的就是这个名字。

        子路由在固件里同样是 HostInfo 的一条记录（VendorClassID=router，
        ID 是 Hosts.Host.N. 这种设备路径），所以复用同一个接口即可；
        我们只是没把它放进设备列表，节点卡上单独给入口。
        真机字段：IsSlave/IsSetupSlave、HiLinkDevice=True、ID 是完整路径。
        """
        sub = {
            "ID": "InternetGatewayDevice.LANDevice.1.Hosts.Host.12.",
            "MACAddress": "AA:BB:CC:DD:EE:09", "HostName": "子路由-02",
            "ActualName": "", "Active": 1, "VendorClassID": "router",
            "HiLinkDevice": True, "IsSlave": True, "IsSetupSlave": False,
            "InterfaceType": "LAN", "Layer2Interface": "LAN1", "rate": 2500,
        }
        r = FakeRouter(hosts=[sub])
        res = make_node(r).rename_host("aa:bb:cc:dd:ee:09", "  书房节点  ")
        self.assertTrue(res["ok"])
        p = r.posts[-1]
        self.assertEqual(p["name"], "system/changedevicename")
        self.assertEqual(p["data"], [{
            "ActualName": "书房节点",
            "ID": "InternetGatewayDevice.LANDevice.1.Hosts.Host.12.",
        }])


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
        for key in ("config2g", "config5g"):
            cfg = p["data"][key]
            macs = [e["MACAddress"] for e in cfg["BMacFilters"]]
            self.assertIn(HOST["MACAddress"], macs)
            self.assertNotIn(HOST["MACAddress"],
                             [e["MACAddress"] for e in cfg["WMacFilters"]])

    def test_payload_matches_firmware_shape(self):
        """写入体的形状必须和固件一致，否则固件回成功但什么都不做。

        固件 c-9.js changeBlack → createSubmitData 的转换规则：
        键名以 Addresses 结尾的换成 Filters（并把 MAC 改成 Mac），其余原样带过；
        整体是 {config2g, config5g} 的对象，不是 GET 那个数组。
        """
        wl = [{"ID": "Radio.1.Ssid.1.", "FrequencyBand": "2.4GHz",
               "MACAddressControlEnabled": True, "MacFilterPolicy": 0,
               "WMACAddresses": [], "BMACAddresses": []},
              {"ID": "Radio.2.Ssid.1.", "FrequencyBand": "5GHz",
               "MACAddressControlEnabled": True, "MacFilterPolicy": 0,
               "WMACAddresses": [], "BMACAddresses": []}]
        r = FakeRouter(hosts=[dict(HOST)], wl=wl)
        make_node(r).set_host_blacklist(HOST["MACAddress"], True)
        data = r.posts[-1]["data"]
        self.assertIsInstance(data, dict, "写入体必须是对象，不能是 GET 的数组")
        self.assertEqual(set(data), {"config2g", "config5g"})
        for key in ("config2g", "config5g"):
            cfg = data[key]
            self.assertIn("BMacFilters", cfg)
            self.assertIn("WMacFilters", cfg)
            self.assertNotIn("BMACAddresses", cfg, "GET 的字段名固件不认")
            self.assertNotIn("WMACAddresses", cfg, "GET 的字段名固件不认")
        # ID / 频段 / 总开关 / 策略要原样带回去，否则固件会当成整条配置被重置
        self.assertEqual(data["config2g"]["ID"], "Radio.1.Ssid.1.")
        self.assertEqual(data["config2g"]["FrequencyBand"], "2.4GHz")
        self.assertEqual(data["config5g"]["FrequencyBand"], "5GHz")
        self.assertIs(data["config2g"]["MACAddressControlEnabled"], True)
        self.assertEqual(data["config5g"]["MacFilterPolicy"], 0)

    def test_bands_are_mapped_by_frequency_not_by_position(self):
        """即使固件把两个频段顺序反了，也不能把 5G 的配置塞进 config2g。"""
        wl = [{"FrequencyBand": "5GHz", "MACAddressControlEnabled": True,
               "WMACAddresses": [], "BMACAddresses": []},
              {"FrequencyBand": "2.4GHz", "MACAddressControlEnabled": True,
               "WMACAddresses": [], "BMACAddresses": []}]
        r = FakeRouter(hosts=[dict(HOST)], wl=wl)
        make_node(r).set_host_blacklist(HOST["MACAddress"], True)
        self.assertEqual(r.posts[-1]["data"]["config5g"]["FrequencyBand"], "5GHz")
        self.assertEqual(r.posts[-1]["data"]["config2g"]["FrequencyBand"], "2.4GHz")

    def test_success_but_no_change_is_reported_as_failure(self):
        """固件「回成功但不照做」时必须报失败，不能让界面显示已加入。

        这是 1.2.6 的真实故障现场：旧的写入体是 GET 的数组形状，
        固件收下、回 {}、名单一点没变，界面上却提示成功。
        """
        r = FakeRouter(hosts=[dict(HOST)], apply_writes=False)
        res = make_node(r).set_host_blacklist(HOST["MACAddress"], True)
        self.assertFalse(res["ok"])
        self.assertIn("没生效", res["error"])

    def test_remove_puts_mac_back_to_whitelist(self):
        r = FakeRouter(hosts=[dict(HOST)])
        n = make_node(r)
        n.set_host_blacklist(HOST["MACAddress"], True)
        n.set_host_blacklist(HOST["MACAddress"], False)
        for key in ("config2g", "config5g"):
            cfg = r.posts[-1]["data"][key]
            self.assertNotIn(HOST["MACAddress"],
                             [e["MACAddress"] for e in cfg["BMacFilters"]])
            self.assertIn(HOST["MACAddress"],
                          [e["MACAddress"] for e in cfg["WMacFilters"]])

    def test_idempotent_add(self):
        r = FakeRouter(hosts=[dict(HOST)])
        n = make_node(r)
        n.set_host_blacklist(HOST["MACAddress"], True)
        n.set_host_blacklist(HOST["MACAddress"], True)
        cfg = r.posts[-1]["data"]["config2g"]
        self.assertEqual(len([e for e in cfg["BMacFilters"]
                              if e["MACAddress"] == HOST["MACAddress"]]), 1)

    def test_requires_master_switch(self):
        wl = [{"MACAddressControlEnabled": False, "WMACAddresses": [], "BMACAddresses": []}]
        res = make_node(FakeRouter(hosts=[dict(HOST)], wl=wl)).set_host_blacklist(
            HOST["MACAddress"], True)
        self.assertFalse(res["ok"])
        self.assertIn("总开关", res["error"])

    def test_rejects_when_router_is_whitelist_mode(self):
        """MacFilterPolicy=1 是白名单模式，这时往黑名单加设备固件会忽略 —— 必须拒掉。

        真机取证：ntwk/wlanfilterenhance 返回两个频段对象，字段为
        MACAddressControlEnabled / MacFilterPolicy / FrequencyBand /
        WMACAddresses / BMACAddresses；MEDUSA2-BR80 出厂 MacFilterPolicy=0（黑名单模式）。
        """
        wl = [{"MACAddressControlEnabled": True, "MacFilterPolicy": 1,
               "FrequencyBand": "2.4GHz", "WMACAddresses": [], "BMACAddresses": []},
              {"MACAddressControlEnabled": True, "MacFilterPolicy": 1,
               "FrequencyBand": "5GHz", "WMACAddresses": [], "BMACAddresses": []}]
        router = FakeRouter(hosts=[dict(HOST)], wl=wl)
        res = make_node(router).set_host_blacklist(HOST["MACAddress"], True)
        self.assertFalse(res["ok"])
        self.assertIn("白名单模式", res["error"])
        self.assertEqual(router.posts, [], "白名单模式下不该发出写入请求")

    def test_blacklist_mode_policy_zero_still_works(self):
        """MacFilterPolicy=0 是黑名单模式（真机默认），不能被误判成白名单。"""
        wl = [{"MACAddressControlEnabled": True, "MacFilterPolicy": 0,
               "FrequencyBand": "2.4GHz", "WMACAddresses": [], "BMACAddresses": []},
              {"MACAddressControlEnabled": True, "MacFilterPolicy": 0,
               "FrequencyBand": "5GHz", "WMACAddresses": [], "BMACAddresses": []}]
        router = FakeRouter(hosts=[dict(HOST)], wl=wl)
        res = make_node(router).set_host_blacklist(HOST["MACAddress"], True)
        self.assertTrue(res["ok"], res.get("error"))
        self.assertEqual(len(router.posts), 1)

    def test_missing_policy_field_is_not_treated_as_whitelist(self):
        """老固件可能没有 MacFilterPolicy 字段，不能因此拒掉。"""
        wl = [{"MACAddressControlEnabled": True, "WMACAddresses": [], "BMACAddresses": []},
              {"MACAddressControlEnabled": True, "WMACAddresses": [], "BMACAddresses": []}]
        res = make_node(FakeRouter(hosts=[dict(HOST)], wl=wl)).set_host_blacklist(
            HOST["MACAddress"], True)
        self.assertTrue(res["ok"], res.get("error"))

    def test_capacity_limited(self):
        """容量看 deviceinfo.MacFilterCapacity（真机 256），不是固件前端老默认的 32。"""
        full = [{"MACAddress": "00:00:00:00:00:%02X" % (i % 256), "HostName": ""}
                for i in range(256)]
        wl = [{"MACAddressControlEnabled": True, "WMACAddresses": [], "BMACAddresses": list(full)},
              {"MACAddressControlEnabled": True, "WMACAddresses": [], "BMACAddresses": list(full)}]
        res = make_node(FakeRouter(hosts=[dict(HOST)], wl=wl)).set_host_blacklist(
            HOST["MACAddress"], True)
        self.assertFalse(res["ok"])
        self.assertIn("满", res["error"])
        self.assertIn("256", res["error"])

    def test_capacity_falls_back_when_device_lacks_field(self):
        """老固件没有 MacFilterCapacity 时退回 32，避免把上限当成无限。"""
        full = [{"MACAddress": "00:00:00:00:00:%02X" % i, "HostName": ""} for i in range(32)]
        wl = [{"MACAddressControlEnabled": True, "WMACAddresses": [], "BMACAddresses": list(full)},
              {"MACAddressControlEnabled": True, "WMACAddresses": [], "BMACAddresses": list(full)}]
        res = make_node(FakeRouter(hosts=[dict(HOST)], wl=wl, capacity=0)).set_host_blacklist(
            HOST["MACAddress"], True)
        self.assertFalse(res["ok"])
        self.assertIn("32", res["error"])


if __name__ == "__main__":
    unittest.main()
