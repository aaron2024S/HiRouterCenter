# -*- coding: utf-8 -*-
"""Mesh 拓扑：子路由识别、设备归属、以及「拓扑不可用」时的降级。

结构依据（免登录逆向固件前端，chunk 9 = 终端页）：
    device/topology 返回顶层数组，每项一个路由器节点
    {MACAddress, HiLinkType, ConnectedDevices:[...], routerSelf}
    "Device" === node.HiLinkType → 这条是路由器/子路由
    routerSelf == 1            → 主路由自己
    节点下挂的终端在它的 ConnectedDevices 里（多层可递归）
"""
import threading
import unittest

from app import node as nd
from app.node import Node, parse_topology
from app.router import NotLoggedIn, RouterError


class FakeSyncer:
    def __init__(self):
        self.lock = threading.RLock()
        self.logins = 0

    def ensure_login(self):
        self.logins += 1
        return True

    def login_backoff_remaining(self):
        return 0

    @property
    def last_error(self):
        return ""


class FakeRouter:
    """只实现测试要用到的接口；其余 GET 会抛错，用来发现「偷偷多打了请求」。"""

    def __init__(self, hosts=None, topology=None, topo_error=None):
        self.logged_in = True
        self.hosts = hosts if hosts is not None else []
        self.topology = topology if topology is not None else []
        self.topo_error = topo_error            # NotLoggedIn(...) / RouterError(...)
        self.topo_gets = 0

    def check_session(self):
        return True

    def get(self, name, params=None):
        if name == "HostInfo":
            return self.hosts
        if name == "device/topology":
            self.topo_gets += 1
            if self.topo_error:
                raise self.topo_error
            return self.topology
        if name == "ntwk/wlanfilterenhance":
            return []
        raise AssertionError("假路由器没实现 GET " + name)


def make_node(router):
    n = Node.__new__(Node)
    n.router = router
    n.syncer = FakeSyncer()
    n.cfg = type("C", (), {"state_file": "", "rules": []})()
    return n


def term(mac, name="终端", active=1):
    return {"MACAddress": mac, "HostName": name, "Active": active,
            "Ipv6Addrs": [{"Ipv6Addr": "240e:3a5:4801:1600::a1"}]}


MAIN_MAC, LIVING_MAC, BED_MAC = "3C:7C:3F:11:22:33", "AA:BB:CC:DD:EE:01", "AA:BB:CC:DD:EE:02"


def sample_topology():
    """主路由 + 两个子路由，各自挂终端（固件那种扁平结构）。"""
    return [
        {"MACAddress": MAIN_MAC, "HiLinkType": "Device", "routerSelf": 1,
         "HostName": "Q7 网线版", "ConnectedDevices": [
             term("00:11:32:7A:9B:1C", "NAS"), term("48:2C:A0:19:5D:73", "冰箱", 0)]},
        {"MACAddress": LIVING_MAC, "HiLinkType": "Device", "routerSelf": 0,
         "HostName": "客厅子路由", "ConnectedDevices": [
             term("A4:5E:60:1B:22:9C", "手机"), term("3C:CD:5D:88:41:E7", "平板")]},
        {"MACAddress": BED_MAC, "HiLinkType": "Device", "routerSelf": 0,
         "HostName": "卧室子路由", "ConnectedDevices": [term("1C:1B:0D:5E:88:A3", "台式机")]},
    ]


def sample_hosts():
    """HostInfo 里节点和终端都在（固件就是这样，我们得自己排掉节点）。"""
    rows = []
    for mac, name in ((MAIN_MAC, "Q7 网线版"), (LIVING_MAC, "客厅子路由"),
                      (BED_MAC, "卧室子路由")):
        rows.append({"MACAddress": mac, "HostName": name, "Active": 1})
    for mac, name in (("00:11:32:7A:9B:1C", "NAS"), ("A4:5E:60:1B:22:9C", "手机"),
                      ("3C:CD:5D:88:41:E7", "平板"), ("1C:1B:0D:5E:88:A3", "台式机")):
        rows.append({"MACAddress": mac, "HostName": name, "Active": 1})
    return rows


class ParseTopologyTest(unittest.TestCase):
    def test_nodes_and_owner(self):
        nodes, owner = parse_topology(sample_topology())
        self.assertEqual([n["key"] for n in nodes],
                         [nd.discover.norm_mac(MAIN_MAC),
                          nd.discover.norm_mac(LIVING_MAC),
                          nd.discover.norm_mac(BED_MAC)])
        self.assertTrue(nodes[0]["self"])
        self.assertFalse(nodes[1]["self"])
        self.assertEqual(nodes[0]["name"], "Q7 网线版")
        # 归属：终端 → 所在节点
        self.assertEqual(owner[nd.discover.norm_mac("A4:5E:60:1B:22:9C")],
                         nd.discover.norm_mac(LIVING_MAC))
        self.assertEqual(owner[nd.discover.norm_mac("1C:1B:0D:5E:88:A3")],
                         nd.discover.norm_mac(BED_MAC))
        self.assertEqual(owner[nd.discover.norm_mac("00:11:32:7A:9B:1C")],
                         nd.discover.norm_mac(MAIN_MAC))
        # 节点自己不是别人的终端
        self.assertNotIn(nd.discover.norm_mac(LIVING_MAC), owner)

    def test_main_router_sorted_first(self):
        tree = list(reversed(sample_topology()))
        nodes, _ = parse_topology(tree)
        self.assertTrue(nodes[0]["self"])

    def test_nested_child_node(self):
        """子路由嵌在主路由的 ConnectedDevices 里时，归属与 parent 都要对。"""
        tree = [{"MACAddress": MAIN_MAC, "HiLinkType": "Device", "routerSelf": 1,
                 "ConnectedDevices": [
                     term("00:11:32:7A:9B:1C", "NAS"),
                     {"MACAddress": BED_MAC, "HiLinkType": "Device",
                      "ConnectedDevices": [term("1C:1B:0D:5E:88:A3", "台式机")]}]}]
        nodes, owner = parse_topology(tree)
        self.assertEqual(len(nodes), 2)
        bed = next(n for n in nodes if n["key"] == nd.discover.norm_mac(BED_MAC))
        self.assertEqual(bed["parent"], nd.discover.norm_mac(MAIN_MAC))
        # 子路由下挂的终端归子路由，不归主路由
        self.assertEqual(owner[nd.discover.norm_mac("1C:1B:0D:5E:88:A3")],
                         nd.discover.norm_mac(BED_MAC))

    def test_data_wrapper(self):
        nodes, owner = parse_topology({"data": sample_topology()})
        self.assertEqual(len(nodes), 3)
        self.assertTrue(owner)

    def test_field_name_variants(self):
        """固件版本不同字段名会飘：MacAddress / hilinktype / connectedDevices 都得认。"""
        tree = [{"MacAddress": MAIN_MAC, "hilinktype": "device", "RouterSelf": 1,
                 "connectedDevices": [term("00:11:32:7A:9B:1C")]}]
        nodes, owner = parse_topology(tree)
        self.assertEqual(len(nodes), 1)
        self.assertTrue(nodes[0]["self"])
        self.assertIn(nd.discover.norm_mac("00:11:32:7A:9B:1C"), owner)

    def test_garbage_returns_none(self):
        for bad in (None, [], {}, "x", [1, 2], [{}]):
            nodes, owner = parse_topology(bad)
            self.assertIsNone(nodes, bad)
            self.assertEqual(owner, {})

    def test_only_terminals_is_not_topology(self):
        """只有终端、没有任何 routerSelf/Device 节点 → 认不出拓扑。"""
        nodes, _ = parse_topology([{"MACAddress": "00:11:32:7A:9B:1C", "HostName": "NAS"}])
        self.assertIsNone(nodes)


class HostRowsMeshTest(unittest.TestCase):
    def test_nodes_excluded_from_device_list(self):
        n = make_node(FakeRouter(hosts=sample_hosts(), topology=sample_topology()))
        rows = n._host_rows()
        macs = {r["mac"] for r in rows}
        self.assertEqual(macs, {"00:11:32:7A:9B:1C", "A4:5E:60:1B:22:9C",
                                "3C:CD:5D:88:41:E7", "1C:1B:0D:5E:88:A3"})

    def test_rows_carry_node_key(self):
        n = make_node(FakeRouter(hosts=sample_hosts(), topology=sample_topology()))
        rows = {r["mac"]: r for r in n._host_rows()}
        self.assertEqual(rows["A4:5E:60:1B:22:9C"]["node"], nd.discover.norm_mac(LIVING_MAC))
        self.assertEqual(rows["1C:1B:0D:5E:88:A3"]["node"], nd.discover.norm_mac(BED_MAC))

    def test_vendor_class_excludes_without_topology(self):
        """拓扑读不到时，靠 VendorClassID 也能把子路由排掉（降级路径）。"""
        hosts = [
            {"MACAddress": "AA:00:00:00:00:01", "HostName": "子路由",
             "VendorClassID": "HUAWEI-router-Q6"},
            {"MACAddress": "AA:00:00:00:00:02", "HostName": "电力猫",
             "VendorClassID": "plcap-device"},
            {"MACAddress": "AA:00:00:00:00:03", "HostName": "中继",
             "VendorClassID": "Repeater"},
            {"MACAddress": "AA:00:00:00:00:04", "HostName": "手机",
             "VendorClassID": "android-dhcp-13"},
        ]
        n = make_node(FakeRouter(hosts=hosts, topology=[]))
        rows = n._host_rows()
        self.assertEqual([r["mac"] for r in rows], ["AA:00:00:00:00:04"])

    def test_ordinary_device_kept_when_no_topology(self):
        n = make_node(FakeRouter(hosts=sample_hosts(), topology=[]))
        # 没有拓扑也没有 VendorClassID 标记 → 节点留在列表里（不敢瞎猜）
        self.assertEqual(len(n._host_rows()), 7)


class MeshViewTest(unittest.TestCase):
    def test_view_fills_name_from_hostinfo(self):
        tree = sample_topology()
        tree[1]["HostName"] = ""            # 固件没给名字
        hosts = sample_hosts()
        n = make_node(FakeRouter(hosts=hosts, topology=tree))
        view = n._mesh_view(hosts)
        self.assertTrue(view["ok"])
        self.assertTrue(view["grouped"])
        self.assertEqual(len(view["nodes"]), 3)
        living = next(x for x in view["nodes"] if x["key"] == nd.discover.norm_mac(LIVING_MAC))
        self.assertEqual(living["name"], "客厅子路由")        # 从 HostInfo 补的
        self.assertFalse(living["self"])

    def test_view_falls_back_to_model_then_mac(self):
        tree = [{"MACAddress": BED_MAC, "HiLinkType": "Device",
                 "DeviceModel": "华为路由 Q6"}]
        n = make_node(FakeRouter(hosts=[], topology=tree))
        view = n._mesh_view([])
        self.assertEqual(view["nodes"][0]["name"], "华为路由 Q6")

        tree2 = [{"MACAddress": BED_MAC, "HiLinkType": "Device"}]
        n2 = make_node(FakeRouter(hosts=[], topology=tree2))
        self.assertEqual(n2._mesh_view([])["nodes"][0]["name"], "AA:BB:CC:DD:EE:02")

    def test_no_terminal_owner_means_not_grouped(self):
        """拓扑只有节点、没有终端归属 → grouped=False，前端不显示下拉。"""
        tree = [{"MACAddress": MAIN_MAC, "HiLinkType": "Device", "routerSelf": 1,
                 "ConnectedDevices": []}]
        n = make_node(FakeRouter(hosts=sample_hosts(), topology=tree))
        view = n._mesh_view(sample_hosts())
        self.assertTrue(view["ok"])
        self.assertFalse(view["grouped"])

    def test_router_error_degrades(self):
        n = make_node(FakeRouter(hosts=sample_hosts(),
                                 topo_error=RouterError("404 不存在")))
        view = n._mesh_view(sample_hosts())
        self.assertFalse(view["ok"])
        self.assertEqual(view["nodes"], [])
        # 设备列表照常（没有 VendorClassID 就不瞎排）
        self.assertEqual(len(n._host_rows()), 7)

    def test_not_logged_in_switches_off_and_relogs(self):
        """固件用 404 隐藏不支持的路径，router 层会顺手注销会话 —— 必须自愈。"""
        r = FakeRouter(hosts=sample_hosts(), topo_error=NotLoggedIn("404"))
        n = make_node(r)
        self.assertIsNone(n._read_mesh())
        self.assertTrue(n._mesh_off)
        self.assertEqual(n.syncer.logins, 1)          # 补登录了一次
        # 之后不再撞这个接口（撞一次就注销一次会话，代价太大）
        before = r.topo_gets
        self.assertIsNone(n._mesh())
        self.assertIsNone(n._mesh())
        self.assertEqual(r.topo_gets, before)

    def test_topology_cached(self):
        r = FakeRouter(hosts=sample_hosts(), topology=sample_topology())
        n = make_node(r)
        n._mesh()
        n._mesh()
        n._host_rows()
        self.assertEqual(r.topo_gets, 1)              # 命中缓存，只打了一次

    def test_grouped_with_sample(self):
        n = make_node(FakeRouter(hosts=sample_hosts(), topology=sample_topology()))
        view = n._mesh_view(sample_hosts())
        self.assertTrue(view["grouped"])
        self.assertEqual(len(view["nodes"]), 3)

    def test_nodes_and_terminals_share_mac_key_format(self):
        """归属表里的 key 与设备行的 node 必须是同一种格式（norm 过的 12 位小写）。"""
        n = make_node(FakeRouter(hosts=sample_hosts(), topology=sample_topology()))
        view = n._mesh_view(sample_hosts())
        keys = {x["key"] for x in view["nodes"]}
        for row in n._host_rows():
            if row["node"]:
                self.assertIn(row["node"], keys)


class NodeLinkTest(unittest.TestCase):
    """节点卡上的「回传链路」：子路由自己那条 HostInfo 里的连接方式与协商速率。

    字段依据真机（Q7 网线版，4 个子路由全走网线）：
        InterfaceType=LAN  Layer2Interface=LAN1…LAN4  rate=2500  PhyType=2500  rssi=0
    拓扑接口本身只给 MAC / 名字 / 下挂设备，链路信息一概没有 —— 只能从这里取。
    主路由在 HostInfo 里**没有记录**（它自己就是本机），所以这四个字段必须为空，
    前端据此不画链路行。
    """

    def _hosts(self):
        return [
            # 有线子路由：插在 LAN1，2.5G 口
            {"MACAddress": LIVING_MAC, "HostName": "客厅子路由", "Active": 1,
             "InterfaceType": "LAN", "Layer2Interface": "LAN1",
             "rate": 2500, "PhyType": 2500, "rssi": 0,
             "ID": "InternetGatewayDevice.LANDevice.1.Hosts.Host.12."},
            # 无线回传：5G，协商 1921，信号是负数（不能被夹到 0）
            {"MACAddress": BED_MAC, "HostName": "卧室子路由", "Active": 1,
             "InterfaceType": "5GHZ", "rate": "1921", "rssi": "-47",
             "ID": "InternetGatewayDevice.LANDevice.1.Hosts.Host.28."},
        ]

    def _view(self):
        hosts = self._hosts()
        n = make_node(FakeRouter(hosts=hosts, topology=sample_topology()))
        return {x["key"]: x for x in n._mesh_view(hosts)["nodes"]}

    def test_wired_link_carries_port_and_rate(self):
        n = self._view()[nd.discover.norm_mac(LIVING_MAC)]
        self.assertEqual(n["iface"], "LAN")
        self.assertEqual(n["layer2"], "LAN1")
        self.assertEqual(n["rate"], 2500)
        self.assertEqual(n["rssi"], 0)
        self.assertTrue(n["id"])                 # 有 ID 才改得了名

    def test_wireless_link_keeps_negative_rssi(self):
        n = self._view()[nd.discover.norm_mac(BED_MAC)]
        self.assertEqual(n["iface"], "5GHZ")
        self.assertEqual(n["layer2"], "")
        self.assertEqual(n["rate"], 1921)        # 字符串也能认
        self.assertEqual(n["rssi"], -47)         # 负数原样保留

    def test_main_router_has_no_link(self):
        """主路由在 HostInfo 里没有记录 → 链路字段全空，前端不画那一行。"""
        n = self._view()[nd.discover.norm_mac(MAIN_MAC)]
        self.assertTrue(n["self"])
        self.assertEqual((n["iface"], n["layer2"], n["rate"], n["rssi"], n["id"]),
                         ("", "", 0, 0, ""))


if __name__ == "__main__":
    unittest.main()
