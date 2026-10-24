# -*- coding: utf-8 -*-
"""
离线单元测试：用假路由器验证「发现 → 比对 → 写入」的核心逻辑。
不联网、不需要真实设备，可在任何装了 Python 3.9+ 的机器上跑：

    python -m unittest discover -s tests -v
"""
import itertools
import json
import os
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import discover, tasks as tk, trustlist, wol  # noqa: E402
from app.config import Config, Rule  # noqa: E402
from app.node import Node  # noqa: E402
from app.settings import SettingsError  # noqa: E402
from app.sync import Syncer  # noqa: E402

NAS_MAC = "00:11:22:AA:BB:CC"
OLD_ADDR = "240e:3a4:48ff:6d10:7173:1ffc:64ed:82c0"
NEW_ADDR = "240e:3a5:483b:2f00:7173:1ffc:64ed:82c0"
# OLD_ADDR 的「固件风格」等价写法：全大写 + 补齐前导零 + 不压缩。
# 用来模拟路由器回读白名单时返回的格式与 HostInfo 不一致的情形。
OLD_ADDR_UGLY = "240E:03A4:48FF:6D10:7173:1FFC:64ED:82C0"

# 同一台设备上的第二个/第三个全局 IPv6：前缀相同，只有后 64 位不同。
# 现场就是这种情形 —— HostInfo 给的顺序里可能有不生效的那一个。
SEC_ADDR = "240e:3a5:483b:2f00:4006:3465:8422:000f"
THIRD_ADDR = "240e:3a5:483b:2f00:dead:beef:cafe:0001"


def C(a):
    """地址的规范形式。canon() 会把 `:000f` 压缩成 `:f`、大写转小写，
    所以断言里一律用它 —— 直接比原始常量会因为写法差异假失败。"""
    return discover.canon(a)


class FakeRouter:
    """最小可用的假路由器：只实现本程序用到的几个接口。"""

    def __init__(self, enabled=True, entries=None, hosts=None):
        # enabled 默认 True：绝大多数用例假设总开关开着（开着才会同步）；
        # 专门测「关 = 待机」的用例显式传 enabled=False。
        self.logged_in = True
        self.username = "admin"
        self.level = 2
        self.writes = []
        self.enabled = enabled
        self.entries = list(entries or [])
        self.hosts = hosts or [{
            "MACAddress": NAS_MAC,
            "HostName": "DiskStation",
            "IPAddress": "192.168.3.5",
            "IPv6Address": "fe80::211:22ff:feaa:bbcc",
            "Ipv6Addrs": [{"Ipv6Addr": OLD_ADDR}],
        }]

    # --- 客户端接口 ---
    def check_session(self):
        return True

    def login(self, password=None):
        self.logged_in = True
        return {"username": "admin", "level": 2, "server_signature_verified": True}

    def get(self, name, params=None):
        if name == "ip6firewall_enable":
            return {"Enable": self.enabled}
        if name == "ip6firewall_trustlist":
            return [dict(e) for e in self.entries]
        if name == "HostInfo":
            return self.hosts
        raise AssertionError(f"假路由器没实现 GET {name}")

    def post(self, name, data=None, wrapped=True, action=None):
        self.writes.append({"name": name, "action": action, "data": data})
        if name == "ip6firewall_enable":
            self.enabled = bool((data or {}).get("Enable"))
            return {}
        if name != "ip6firewall_trustlist":
            raise AssertionError(f"假路由器没实现 POST {name}")

        if action == "create":
            item = dict(data)
            item["ID"] = f"InternetGatewayDevice.X_FireWall.Ipv6.Trustlist.{len(self.entries) + 1}."
            self.entries.append(item)
            return {}
        if action == "update":
            for i, e in enumerate(self.entries):
                if e.get("ID") == data.get("ID"):
                    self.entries[i] = dict(data)
                    return {}
            return {"errcode": 1, "errmsg": "not found"}
        if action == "delete":
            before = len(self.entries)
            # 固件 delete 用小写 ip 键：按 ID 删即可
            self.entries = [e for e in self.entries if e.get("ID") != data.get("ID")]
            return {} if len(self.entries) < before else {"errcode": 1}
        raise AssertionError(f"未知 action {action}")


# 累计计数文件的落盘位置。必须隔离：Config 的默认值是 /data/state.json，
# 而在 Windows 上它会被解析成<当前盘>:\data\state.json —— 测试真跑出写入就会
# 往盘根建目录写文件。这里给每个用例发一个独立文件，顺带避免用例之间串味。
_STATE_DIR = tempfile.mkdtemp(prefix="ipv6sync-test-state-")
_state_seq = itertools.count(1)


def make_cfg(**kw) -> Config:
    # 规则不带 MAC = 「本机网卡」取址路径（环境变量来的老配置形态）；
    # 绑 MAC 的设备规则（路由器第一条）由 TestDeviceRule 单独覆盖。
    cfg = Config(
        host="192.168.3.1", username="admin", password="x",
        session_file=None, poll_interval=1,
        rules=[Rule(name="NAS", port=None, remote_ip="::/0", mac=None)],
        state_file=os.path.join(_STATE_DIR, f"state-{next(_state_seq)}.json"),
    )
    for k, v in kw.items():
        setattr(cfg, k, v)
    return cfg


class LocalNetStub:
    """给「本机网卡」装上假数据。

    取址流程现在**固定读本机网卡**（/proc/net/if_inet6、/sys/class/net），
    而测试机（Windows、多数 CI）上这些路径不存在 —— 不装这个桩，同步路径
    根本走不到，用例会集体静默变成 "skip"。
    """

    LOCAL_ADDRS = [OLD_ADDR]           # 默认：网卡上就一个全局地址

    def setUp(self):
        self._net_saved = (discover.local_candidates, discover.local_macs,
                           discover.temporary_set)
        self.patch_local(self.LOCAL_ADDRS, {discover.norm_mac(NAS_MAC)})

    def tearDown(self):
        (discover.local_candidates, discover.local_macs,
         discover.temporary_set) = self._net_saved

    def patch_local(self, addrs, macs=None, temp=None):
        """改写「网卡上有什么」。不需要手动还原 —— tearDown 统一恢复。"""
        discover.local_candidates = (
            lambda: [discover.canon(a) or a for a in addrs])
        discover.temporary_set = lambda: set(temp or ())
        if macs is not None:
            discover.local_macs = lambda: set(macs)


class TestAddressHelpers(unittest.TestCase):
    def test_canon(self):
        self.assertEqual(discover.canon("240E:3A4:48FF:6D10::82C0"),
                         "240e:3a4:48ff:6d10::82c0")
        self.assertEqual(discover.canon("240e:3a4::1/64"), "240e:3a4::1")
        self.assertEqual(discover.canon("fe80::1%eth0"), "fe80::1")
        self.assertIsNone(discover.canon("not-an-ip"))
        self.assertIsNone(discover.canon(""))

    def test_is_usable_filters(self):
        self.assertTrue(discover.is_usable(OLD_ADDR))
        self.assertFalse(discover.is_usable("fe80::1"))         # 链路本地
        self.assertFalse(discover.is_usable("::1"))             # 回环
        self.assertFalse(discover.is_usable("ff02::1"))         # 组播
        self.assertFalse(discover.is_usable("::ffff:192.168.1.1"))  # v4 映射
        self.assertFalse(discover.is_usable("fc00::1"))         # ULA

    def test_norm_mac(self):
        self.assertEqual(discover.norm_mac("00:11:22:AA:bb:CC"), "001122aabbcc")
        self.assertEqual(discover.norm_mac("00-11-22-aa-bb-cc"), "001122aabbcc")

    def test_rank_puts_temporary_last_without_dropping(self):
        """只有一条排序规则：隐私临时地址靠后；顺序变了但一个都不丢。"""
        stable = "240e:3a5:483b:2f00:aaaa:bbbb:cccc:dddd"
        ranked = discover.rank_candidates([NEW_ADDR, stable],
                                          temp_suspect={NEW_ADDR})
        self.assertEqual(ranked, [stable, NEW_ADDR])
        self.assertEqual(sorted(ranked), sorted([NEW_ADDR, stable]))
        # 没标出临时地址时保持原本的来源顺序（稳定排序）
        self.assertEqual(discover.rank_candidates([NEW_ADDR, stable]),
                         [NEW_ADDR, stable])
        self.assertEqual(discover.rank_candidates([], temp_suspect=set()), [])

    def test_same_addr_ignores_formatting(self):
        """写法不同但地址相同要判等 —— 否则每轮都会白写一次闪存。"""
        self.assertTrue(discover.same_addr(OLD_ADDR, OLD_ADDR_UGLY))
        self.assertTrue(discover.same_addr(OLD_ADDR_UGLY, OLD_ADDR))
        self.assertTrue(discover.same_addr(OLD_ADDR, OLD_ADDR + "/64"))
        self.assertTrue(discover.same_addr(OLD_ADDR, OLD_ADDR))
        self.assertFalse(discover.same_addr(OLD_ADDR, NEW_ADDR))

    def test_same_addr_never_conflates_empty(self):
        """空值/非法值不能被判成与某个真实地址相同（否则该写的就不写了）。"""
        self.assertFalse(discover.same_addr("", OLD_ADDR))
        self.assertFalse(discover.same_addr(None, OLD_ADDR))
        self.assertFalse(discover.same_addr("not-an-ip", OLD_ADDR))


class TestRouterDeviceList(unittest.TestCase):
    """HostInfo 只用来给控制台的「在线设备」页列 MAC / IPv6，不参与取址。"""

    def test_host_candidates_reads_ipv6addrs(self):
        host = {"IPv6Address": "fe80::1",
                "Ipv6Addrs": [{"Ipv6Addr": OLD_ADDR}, {"Ipv6Addr": "fe80::9"}]}
        self.assertEqual(discover.host_candidates(host), [OLD_ADDR])


class TestTrustlistCrud(unittest.TestCase):
    def test_add_then_upsert_unchanged(self):
        r = FakeRouter()
        self.assertEqual(trustlist.upsert(r, "NAS", OLD_ADDR, None, "::/0")[0], "created")
        self.assertEqual(len(r.entries), 1)
        self.assertEqual(trustlist.upsert(r, "NAS", OLD_ADDR, None, "::/0")[0], "unchanged")
        self.assertEqual(len(r.entries), 1)

    def test_upsert_updates_in_place(self):
        r = FakeRouter()
        trustlist.upsert(r, "NAS", OLD_ADDR, None, "::/0")
        action, _ = trustlist.upsert(r, "NAS", NEW_ADDR, None, "::/0")
        self.assertEqual(action, "updated")
        self.assertEqual(len(r.entries), 1)
        self.assertEqual(r.entries[0]["LocalIp"], NEW_ADDR)

    def test_upsert_detects_port_change(self):
        r = FakeRouter()
        trustlist.upsert(r, "NAS", OLD_ADDR, 16669, "::/0")
        self.assertEqual(trustlist.upsert(r, "NAS", OLD_ADDR, 16669, "::/0")[0], "unchanged")
        self.assertEqual(trustlist.upsert(r, "NAS", OLD_ADDR, 80, "::/0")[0], "updated")

    def test_upsert_unchanged_across_formatting(self):
        """固件存的写法与本次传入不同、但地址相同 → unchanged，且一次都不写。"""
        r = FakeRouter(entries=[{"Name": "NAS", "LocalIp": OLD_ADDR_UGLY,
                                 "RemoteIp": "::/0", "Port": -1, "ID": "id1"}])
        action, _ = trustlist.upsert(r, "NAS", OLD_ADDR, None, "::/0")
        self.assertEqual(action, "unchanged")
        self.assertEqual(r.writes, [])

    def test_port_none_becomes_all_ports(self):
        r = FakeRouter()
        trustlist.add(r, "NAS", OLD_ADDR, None, "::/0")
        self.assertEqual(r.entries[0]["Port"], -1)
        trustlist.add(r, "NAS2", OLD_ADDR, "all", "::/0")
        self.assertEqual(r.entries[1]["Port"], -1)

    def test_max_entries_guard(self):
        r = FakeRouter(entries=[{"Name": f"e{i}", "ID": f"id{i}"}
                                for i in range(trustlist.MAX_ENTRIES)])
        with self.assertRaises(Exception):
            trustlist.upsert(r, "NAS", OLD_ADDR, None, "::/0")

    def test_delete_by_id(self):
        r = FakeRouter()
        trustlist.upsert(r, "NAS", OLD_ADDR, None, "::/0")
        entry = trustlist.find_by_name(r, "NAS")
        trustlist.delete(r, entry)
        self.assertEqual(r.entries, [])

    def test_ok_helper(self):
        self.assertTrue(trustlist.ok({}))
        self.assertTrue(trustlist.ok({"errcode": 0}))
        self.assertFalse(trustlist.ok({"errcode": 9003}))
        self.assertTrue(trustlist.ok(None))


class TestSyncer(LocalNetStub, unittest.TestCase):
    def test_creates_entry_when_missing(self):
        r = FakeRouter(entries=[])
        s = Syncer(make_cfg(), r)
        snap = s.tick()
        self.assertTrue(snap["ok"])
        self.assertEqual(snap["rules"]["NAS"]["action"], "created")
        self.assertEqual(r.entries[0]["LocalIp"], OLD_ADDR)
        self.assertEqual(r.entries[0]["Name"], "NAS")

    def test_unchanged_when_address_same(self):
        r = FakeRouter(entries=[{"Name": "NAS", "LocalIp": OLD_ADDR,
                                 "RemoteIp": "::/0", "Port": -1, "ID": "id1"}])
        s = Syncer(make_cfg(), r)
        snap = s.tick()
        self.assertEqual(snap["rules"]["NAS"]["action"], "unchanged")
        self.assertEqual(r.writes, [])          # 没有任何写操作

    def test_firewall_off_skips_sync_and_resumes(self):
        """总开关关闭 = 待机：本轮不写任何条目；重新打开后下一轮自动追平。

        旧行为是开关关着也照样写条目（写上去也不生效，白费 flash）；
        新语义与网页一致：关 = 只观察不写入。
        """
        r = FakeRouter(enabled=False, entries=[])
        s = Syncer(make_cfg(), r)
        snap = s.tick()
        self.assertTrue(snap["ok"])             # 观察轮也算成功
        self.assertFalse(snap["firewall_ipv6_enabled"])
        self.assertEqual(r.writes, [])          # 不写条目
        self.assertFalse(r.enabled)             # 也不会擅自动开关
        # 用户把开关重新打开（比如从网页拨回去）→ 下一轮恢复同步
        r.enabled = True
        snap = s.tick()
        self.assertEqual(snap["rules"]["NAS"]["action"], "created")
        self.assertEqual(r.entries[0]["LocalIp"], C(OLD_ADDR))

    def test_unchanged_when_router_formats_address_differently(self):
        """回归：路由器回读的地址写法与 HostInfo 不同（大写/未压缩），
        但地址其实没变 —— 必须判为无变化。

        以前的实现直接比字符串，这种固件会让每一轮轮询都误判成「变了」并
        重写一次白名单；白名单写入是 flash 操作，长期反复写毫无意义还伤寿命。
        """
        r = FakeRouter(entries=[{"Name": "NAS", "LocalIp": OLD_ADDR_UGLY,
                                 "RemoteIp": "::/0", "Port": -1, "ID": "id1"}])
        s = Syncer(make_cfg(), r)
        for _ in range(3):                      # 连跑三轮，一轮都不能写
            snap = s.tick()
            self.assertEqual(snap["rules"]["NAS"]["action"], "unchanged")
        self.assertEqual(r.writes, [])
        self.assertEqual(s.total_writes, 0)
        self.assertEqual(r.entries[0]["LocalIp"], OLD_ADDR_UGLY)   # 原文没被动过

    def test_follows_ipv6_change(self):
        """核心场景：本机网卡的 IPv6 变了 → 白名单原地更新。"""
        r = FakeRouter(entries=[{"Name": "NAS", "LocalIp": OLD_ADDR,
                                 "RemoteIp": "::/0", "Port": -1, "ID": "id1"}])
        self.patch_local([NEW_ADDR])            # 网卡上现在只剩新地址了
        s = Syncer(make_cfg(), r)
        snap = s.tick()
        self.assertEqual(snap["rules"]["NAS"]["action"], "updated")
        self.assertEqual(len(r.entries), 1)                 # 没有新增条目
        self.assertEqual(r.entries[0]["LocalIp"], C(NEW_ADDR))  # 原地改成新地址
        self.assertEqual(r.entries[0]["ID"], "id1")          # ID 保持不变

    def test_dry_run_never_writes(self):
        r = FakeRouter(entries=[])
        s = Syncer(make_cfg(dry_run=True), r)
        snap = s.tick()
        self.assertEqual(snap["rules"]["NAS"]["action"], "dry-run")
        self.assertEqual(r.writes, [])

    def test_no_address_found_is_skipped_not_crashed(self):
        """网卡上没有可用的全局 IPv6（例如容器没走 host 网络）→ 跳过并说清楚。
        绝不能猜一个地址写上去。"""
        r = FakeRouter(entries=[])
        self.patch_local([])
        s = Syncer(make_cfg(), r)
        snap = s.tick()
        self.assertEqual(snap["rules"]["NAS"]["action"], "skip")
        self.assertEqual(snap["rules"]["NAS"]["error"], "no-address")
        self.assertEqual(r.writes, [])

    def test_verify_failure_is_reported(self):
        """设备 ACK 了但没真保存（写后回读不一致）必须报错，不能静默成功。"""
        class AmnesiacRouter(FakeRouter):
            def post(self, name, data=None, wrapped=True, action=None):
                if name == "ip6firewall_trustlist":
                    self.writes.append({"action": action})
                    return {}          # 假装成功，但不落库
                return super().post(name, data, wrapped, action)

        r = AmnesiacRouter(entries=[])
        s = Syncer(make_cfg(), r)
        snap = s.tick()
        self.assertEqual(snap["rules"]["NAS"]["error"], "verify-failed")

    def test_verify_accepts_equivalent_formatting(self):
        """固件把地址改写成另一种写法（大写）不等于「没保存」，
        回读校验要按规范化地址判等，不能误报 verify-failed。"""
        class NormalizingRouter(FakeRouter):
            def post(self, name, data=None, wrapped=True, action=None):
                res = super().post(name, data, wrapped, action)
                if name == "ip6firewall_trustlist" and action in ("create", "update"):
                    for e in self.entries:
                        if e.get("Name") == (data or {}).get("Name"):
                            e["LocalIp"] = str(e.get("LocalIp") or "").upper()
                return res

        r = NormalizingRouter(entries=[])
        s = Syncer(make_cfg(), r)
        snap = s.tick()
        self.assertIsNone(snap["rules"]["NAS"]["error"])
        self.assertEqual(snap["rules"]["NAS"]["action"], "created")
        self.assertEqual(r.entries[0]["LocalIp"], OLD_ADDR.upper())   # 固件改写成了大写

    def test_rule_mac_not_in_router_table_skips(self):
        """设备规则绑的 MAC 不在路由器设备表里 → 本轮跳过、白名单不动。

        路由器刚重启、表还没重建时就是这种情形 —— 此时绝不能按「没有地址」
        把既有条目清掉，等下一个周期表重建了自然恢复。
        """
        r = FakeRouter(entries=[])
        cfg = make_cfg()
        cfg.rules[0].mac = "AA:BB:CC:DD:EE:FF"           # 表里没有这台
        self.patch_local([OLD_ADDR], set())
        st = Syncer(cfg, r).sync_rule(cfg.rules[0])
        self.assertEqual(st.action, "skip")
        self.assertIn("没有该 MAC", st.detail)
        self.assertEqual(r.entries, [])

    def test_ensure_firewall_on(self):
        r = FakeRouter(enabled=False)
        s = Syncer(make_cfg(ensure_firewall_on=True), r)
        s.tick()
        self.assertTrue(r.enabled)

    def test_firewall_not_touched_by_default(self):
        r = FakeRouter(enabled=False)
        s = Syncer(make_cfg(ensure_firewall_on=False), r)
        s.tick()
        self.assertFalse(r.enabled)


class TestMultiPort(LocalNetStub, unittest.TestCase):
    """多端口支持：PORT 规格解析、多条目展开、缩容清理。"""

    def test_parse_ports(self):
        self.assertEqual(trustlist.parse_ports(None), [-1])
        self.assertEqual(trustlist.parse_ports(""), [-1])
        self.assertEqual(trustlist.parse_ports("-1"), [-1])
        self.assertEqual(trustlist.parse_ports(16669), [16669])
        self.assertEqual(trustlist.parse_ports("16667"), [16667])
        self.assertEqual(trustlist.parse_ports("16667,5005,22"), [16667, 5005, 22])
        self.assertEqual(trustlist.parse_ports(" 16667 ， 5005 "), [16667, 5005])  # 中文逗号+空格
        self.assertEqual(trustlist.parse_ports("16667,16667"), [16667])           # 去重

    def test_parse_ports_rejects_bad_values(self):
        for bad in ("abc", "0", "65536", "80;443"):
            with self.assertRaises(ValueError):
                trustlist.parse_ports(bad)
        # 尾随逗号是合法的（空 token 被忽略）
        self.assertEqual(trustlist.parse_ports("16667,"), [16667])

    def test_rule_accepts_multi_port_spec(self):
        from app.config import Rule
        self.assertEqual(Rule(name="NAS", port="16667,5005").port, "16667,5005")
        self.assertEqual(Rule(name="NAS", port="16667,5005，22").port, "16667,5005,22")
        self.assertIsNone(Rule(name="NAS", port="-1").port)
        self.assertIsNone(Rule(name="NAS", port="").port)
        self.assertEqual(Rule(name="NAS", port="16667").port, 16667)

    def test_entry_names(self):
        self.assertEqual(trustlist.entry_names("NAS", [-1]), [("NAS", -1)])
        self.assertEqual(trustlist.entry_names("NAS", [16667]), [("NAS", 16667)])
        self.assertEqual(trustlist.entry_names("NAS", [16667, 5005]),
                         [("NAS", 16667), ("NAS-5005", 5005)])
        self.assertEqual(trustlist.entry_names("NAS", [16667, 5005, 22]),
                         [("NAS", 16667), ("NAS-5005", 5005), ("NAS-22", 22)])

    def test_sync_creates_entry_per_port(self):
        r = FakeRouter(entries=[])
        cfg = make_cfg()
        cfg.rules[0].port = "16667,5005"
        s = Syncer(cfg, r)
        snap = s.tick()
        self.assertTrue(snap["ok"])
        self.assertEqual({e["Name"] for e in r.entries}, {"NAS", "NAS-5005"})
        by_name = {e["Name"]: e for e in r.entries}
        self.assertEqual(by_name["NAS"]["Port"], 16667)
        self.assertEqual(by_name["NAS-5005"]["Port"], 5005)
        self.assertEqual(by_name["NAS"]["LocalIp"], OLD_ADDR)
        self.assertEqual(by_name["NAS-5005"]["LocalIp"], OLD_ADDR)

    def test_sync_removes_stale_port_entries(self):
        """端口列表缩容后，多出来的条目要被删掉，不会越积越多。"""
        r = FakeRouter(entries=[
            {"Name": "NAS", "LocalIp": OLD_ADDR, "RemoteIp": "::/0",
             "Port": 16667, "ID": "id1"},
            {"Name": "NAS-5005", "LocalIp": OLD_ADDR, "RemoteIp": "::/0",
             "Port": 5005, "ID": "id2"},
            {"Name": "NAS-22", "LocalIp": OLD_ADDR, "RemoteIp": "::/0",
             "Port": 22, "ID": "id3"},
            {"Name": "别的设备-22", "LocalIp": OLD_ADDR, "RemoteIp": "::/0",
             "Port": 22, "ID": "id4"},          # 不是本程序的名字，不能动
        ])
        cfg = make_cfg()
        cfg.rules[0].port = "16667"             # 收缩到只剩 16667
        s = Syncer(cfg, r)
        snap = s.tick()
        self.assertTrue(snap["ok"])
        names = {e["Name"] for e in r.entries}
        self.assertEqual(names, {"NAS", "别的设备-22"})   # NAS-5005 / NAS-22 被清理

    def test_multi_port_shrink_updates_and_cleans(self):
        """从多端口改到另一个多端口：改留下的、删多余的。"""
        r = FakeRouter(entries=[
            {"Name": "NAS", "LocalIp": OLD_ADDR, "RemoteIp": "::/0",
             "Port": 16667, "ID": "id1"},
            {"Name": "NAS-5005", "LocalIp": OLD_ADDR, "RemoteIp": "::/0",
             "Port": 5005, "ID": "id2"},
        ])
        cfg = make_cfg()
        cfg.rules[0].port = "16667,8080"
        s = Syncer(cfg, r)
        snap = s.tick()
        self.assertTrue(snap["ok"])
        by_name = {e["Name"]: e for e in r.entries}
        self.assertEqual(set(by_name), {"NAS", "NAS-8080"})
        self.assertEqual(by_name["NAS"]["Port"], 16667)     # 留下的原地更新
        self.assertEqual(by_name["NAS-8080"]["Port"], 8080)  # 新增

    def test_multi_port_unchanged_writes_nothing(self):
        r = FakeRouter(entries=[
            {"Name": "NAS", "LocalIp": OLD_ADDR, "RemoteIp": "::/0",
             "Port": 16667, "ID": "id1"},
            {"Name": "NAS-5005", "LocalIp": OLD_ADDR, "RemoteIp": "::/0",
             "Port": 5005, "ID": "id2"},
        ])
        cfg = make_cfg()
        cfg.rules[0].port = "16667,5005"
        s = Syncer(cfg, r)
        snap = s.tick()
        self.assertEqual(snap["rules"]["NAS"]["action"], "unchanged")
        self.assertEqual(r.writes, [])


    def test_settings_rejects_bad_port_spec(self):
        """规则列表在保存时就要拦住坏端口规格，不能等同步引擎才炸。"""
        from app import settings as st_mod

        def rules_with(port):
            return {"RULES": [{"name": "A", "mac": "aa:bb:cc:dd:ee:ff",
                               "port": port}]}
        with self.assertRaises(st_mod.SettingsError):
            st_mod.validate_overlay(rules_with("abc"))
        with self.assertRaises(st_mod.SettingsError):
            st_mod.validate_overlay(rules_with("80;443"))
        with self.assertRaises(st_mod.SettingsError):
            st_mod.validate_overlay(rules_with("0"))
        self.assertEqual(
            st_mod.validate_overlay(rules_with("16667,5005"))["RULES"][0]["port"],
            "16667,5005")
        self.assertEqual(
            st_mod.validate_overlay(rules_with("-1"))["RULES"][0]["port"], "-1")


class TestMultiAddress(LocalNetStub, unittest.TestCase):
    """一台设备多个全局 IPv6 时「每个地址各写一条」的行为。

    现场背景：白名单的 LocalIp 是**目的地址匹配规则**，所以必须写"外部真会
    打到、且确实挂在该设备网卡上"的那个地址。一块网卡常同时有 SLAAC 稳定
    地址、RFC 4941 隐私临时地址、DHCPv6 地址，前缀一样、只有后 64 位不同；
    固件给的顺序不代表优先级，只写一条就是赌运气 —— 所以全写，一条都不赌。
    """

    def _router(self, addrs, entries=None, temp=None):
        """装好「网卡上有哪些地址」，再给一个空白的假路由器。"""
        self.patch_local(addrs, {discover.norm_mac(NAS_MAC)}, temp=temp)
        return FakeRouter(entries=entries or [])

    def test_entry_names_multi_address(self):
        self.assertEqual(trustlist.entry_names("NAS", [-1], 0), [("NAS", -1)])
        self.assertEqual(trustlist.entry_names("NAS", [-1], 1), [("NAS@2", -1)])
        self.assertEqual(trustlist.entry_names("NAS", [16667, 5005], 1),
                         [("NAS@2", 16667), ("NAS@2-5005", 5005)])
        # 第 0 个地址必须沿用基础名，否则升级后会把老条目白占一个新名额
        self.assertEqual(trustlist.entry_names("NAS", [16667], 0), [("NAS", 16667)])

    def test_managed_names_of(self):
        entries = [{"Name": "NAS"}, {"Name": "NAS@2"}, {"Name": "NAS@2-5005"},
                   {"Name": "NAS-5005"}, {"Name": "NAS2"}, {"Name": "NAS-备用"},
                   {"Name": "别动我"}, {"Name": ""}]
        self.assertEqual(trustlist.managed_names_of(entries, "NAS"),
                         ["NAS", "NAS@2", "NAS@2-5005", "NAS-5005"])

    def test_creates_entry_per_address(self):
        r = self._router([OLD_ADDR, SEC_ADDR])
        s = Syncer(make_cfg(), r)
        snap = s.tick()
        self.assertTrue(snap["ok"])
        by_name = {e["Name"]: e for e in r.entries}
        self.assertEqual(set(by_name), {"NAS", "NAS@2"})
        self.assertTrue(discover.same_addr(by_name["NAS"]["LocalIp"], OLD_ADDR))
        self.assertTrue(discover.same_addr(by_name["NAS@2"]["LocalIp"], SEC_ADDR))
        st = snap["rules"]["NAS"]
        self.assertEqual(st["addrs"], [C(OLD_ADDR), C(SEC_ADDR)])
        self.assertEqual(st["addr"], C(OLD_ADDR))       # 主地址 = 列表第一个

    def test_multi_address_unchanged_second_round(self):
        """两个地址都已写好 → 第二轮一个字节都不写（写入是 flash 操作）。"""
        r = self._router([OLD_ADDR, SEC_ADDR])
        s = Syncer(make_cfg(), r)
        s.tick()
        r.writes.clear()
        snap = s.tick()
        self.assertEqual(snap["rules"]["NAS"]["action"], "unchanged")
        self.assertEqual(r.writes, [])

    def test_multi_port_expands_grid(self):
        """地址 × 端口 的笛卡尔积：2 个地址 × 2 个端口 = 4 条。"""
        r = self._router([OLD_ADDR, SEC_ADDR])
        cfg = make_cfg()
        cfg.rules[0].port = "16667,5005"
        s = Syncer(cfg, r)
        s.tick()
        self.assertEqual({e["Name"] for e in r.entries},
                         {"NAS", "NAS-5005", "NAS@2", "NAS@2-5005"})
        by_name = {e["Name"]: e for e in r.entries}
        self.assertTrue(discover.same_addr(by_name["NAS@2-5005"]["LocalIp"], SEC_ADDR))
        self.assertEqual(by_name["NAS@2-5005"]["Port"], 5005)

    def test_address_reduction_removes_stale_entry(self):
        """设备地址减少（旧地址过期）→ 对应条目要删掉，不能留着占名额。"""
        r = self._router([OLD_ADDR], entries=[
            {"Name": "NAS", "LocalIp": OLD_ADDR, "RemoteIp": "::/0",
             "Port": -1, "ID": "id1"},
            {"Name": "NAS@2", "LocalIp": SEC_ADDR, "RemoteIp": "::/0",
             "Port": -1, "ID": "id2"},
        ])
        s = Syncer(make_cfg(), r)
        snap = s.tick()
        self.assertTrue(snap["ok"])
        self.assertEqual({e["Name"] for e in r.entries}, {"NAS"})

    def test_cleanup_ignores_user_named_entries(self):
        """只删本程序命名的条目，用户手工加的（哪怕名字很像）一个都不能动。"""
        r = self._router([OLD_ADDR], entries=[
            {"Name": "NAS", "LocalIp": OLD_ADDR, "RemoteIp": "::/0",
             "Port": -1, "ID": "id1"},
            {"Name": "NAS@2", "LocalIp": SEC_ADDR, "RemoteIp": "::/0",
             "Port": -1, "ID": "id2"},          # 本程序命名，该删
            {"Name": "NAS2", "LocalIp": SEC_ADDR, "RemoteIp": "::/0",
             "Port": -1, "ID": "id3"},          # 用户命名，不能删
            {"Name": "NAS-备用", "LocalIp": SEC_ADDR, "RemoteIp": "::/0",
             "Port": -1, "ID": "id4"},          # 用户命名，不能删
            {"Name": "NAS@备用", "LocalIp": SEC_ADDR, "RemoteIp": "::/0",
             "Port": -1, "ID": "id5"},          # @ 后不是数字 → 用户命名
        ])
        s = Syncer(make_cfg(), r)
        s.tick()
        self.assertEqual({e["Name"] for e in r.entries},
                         {"NAS", "NAS2", "NAS-备用", "NAS@备用"})

    def test_temporary_addr_gets_base_name_last(self):
        """隐私临时地址排到后面 —— 只影响谁占基础条目名 NAS，不影响写不写。

        临时地址过期就会换，让它当"主地址"会让白名单里的 NAS 条目频繁改名；
        但**它照样要写**，报文完全可能落在它上面。
        """
        r = self._router([SEC_ADDR, OLD_ADDR], temp={C(SEC_ADDR)})
        s = Syncer(make_cfg(), r)
        snap = s.tick()
        by_name = {e["Name"]: e for e in r.entries}
        self.assertEqual(set(by_name), {"NAS", "NAS@2"})
        self.assertTrue(discover.same_addr(by_name["NAS"]["LocalIp"], OLD_ADDR))
        self.assertTrue(discover.same_addr(by_name["NAS@2"]["LocalIp"], SEC_ADDR))
        self.assertEqual(snap["rules"]["NAS"]["addr"], C(OLD_ADDR))

    def test_writes_every_nic_address(self):
        """核心场景：网卡上有几个全局地址就写几条，一条都不漏。

        路由器设备表记的是 THIRD_ADDR（网卡上早就没了）、也不知道有 SEC_ADDR；
        网卡上现在是 OLD_ADDR + SEC_ADDR。白名单按目的地址匹配，只有网卡上
        真有的地址才收得到包 —— 所以按网卡写，路由器记了什么完全不影响。
        """
        r = self._router([OLD_ADDR, SEC_ADDR])
        cfg = make_cfg()
        st = Syncer(cfg, r).sync_rule(cfg.rules[0])
        self.assertEqual(st.addrs, [C(OLD_ADDR), C(SEC_ADDR)])
        self.assertIn("本机网卡", st.detail)
        self.assertEqual({e["Name"] for e in r.entries}, {"NAS", "NAS@2"})
        addrs = sorted(e["LocalIp"] for e in r.entries)
        self.assertEqual(addrs, sorted([C(OLD_ADDR), C(SEC_ADDR)]))

    def test_room_budget_limits_addresses(self):
        """白名单一共 32 条：只剩 1 个位置时只能写 1 个地址，并给出告警。
        用户手工加的 31 条绝不能被挤掉。"""
        others = [{"Name": f"用户{i}", "LocalIp": OLD_ADDR, "RemoteIp": "::/0",
                   "Port": -1, "ID": f"o{i}"} for i in range(31)]
        r = self._router([OLD_ADDR, SEC_ADDR], entries=others)
        s = Syncer(make_cfg(), r)
        snap = s.tick()
        self.assertTrue(snap["ok"])
        names = {e["Name"] for e in r.entries}
        self.assertEqual(len(r.entries), 32)
        self.assertEqual(names - {f"用户{i}" for i in range(31)}, {"NAS"})
        self.assertIn("名额", snap["rules"]["NAS"]["detail"])

    def test_room_budget_counts_own_entries_as_reusable(self):
        """名额预算里，本程序已有的条目算"可复用"，不该把自己挤掉。"""
        mine = [{"Name": "NAS", "LocalIp": OLD_ADDR, "RemoteIp": "::/0",
                 "Port": -1, "ID": "id1"},
                {"Name": "NAS@2", "LocalIp": SEC_ADDR, "RemoteIp": "::/0",
                 "Port": -1, "ID": "id2"}]
        others = [{"Name": f"用户{i}", "LocalIp": OLD_ADDR, "RemoteIp": "::/0",
                   "Port": -1, "ID": f"o{i}"} for i in range(30)]
        r = self._router([OLD_ADDR, SEC_ADDR], entries=mine + others)
        s = Syncer(make_cfg(), r)
        snap = s.tick()
        # 30 + 2 = 32，已是满的，但两条都是自己的 → 原地更新即可，不该被截断
        self.assertEqual(snap["rules"]["NAS"]["action"], "unchanged")
        self.assertEqual(len(r.entries), 32)

    def test_dry_run_lists_every_address(self):
        r = self._router([OLD_ADDR, SEC_ADDR])
        s = Syncer(make_cfg(dry_run=True), r)
        snap = s.tick()
        st = snap["rules"]["NAS"]
        self.assertEqual(st["action"], "dry-run")
        self.assertEqual(len(st["addrs"]), 2)
        self.assertIn("将写", st["detail"])
        self.assertEqual(r.writes, [])


class TestConfig(unittest.TestCase):
    def test_env_parsing(self):
        env = {
            "ROUTER_HOST": "10.0.0.1", "ROUTER_PASSWORD": "secret",
            "ENTRY_NAME": "MyNAS", "ENTRY_PORT": "16669", "TARGET_MAC": NAS_MAC,
            "POLL_INTERVAL": "30",
        }
        saved = {k: os.environ.get(k) for k in env}
        os.environ.update(env)
        try:
            from app.config import load_config
            cfg = load_config([])
            self.assertEqual(cfg.host, "10.0.0.1")
            self.assertEqual(cfg.rules[0].name, "MyNAS")
            self.assertEqual(cfg.rules[0].port, 16669)
            self.assertEqual(cfg.rules[0].mac, NAS_MAC)
            self.assertEqual(cfg.poll_interval, 30)
            self.assertEqual(cfg.base_url, "http://10.0.0.1")
        finally:
            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v

    def test_removed_keys_are_ignored_but_rest_still_apply(self):
        """旧设置文件里留着本版本已删的项（SOURCE / WRITE_ALL …）。

        读文件必须**忽略那些项、其余照常生效** —— 整份丢弃会让用户此前填的
        路由器密码、条目名一起失效，而人还以为配置没丢，这是最糟的失败方式。
        """
        from app import settings as st_mod
        path = os.path.join(_STATE_DIR, "legacy-settings.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"ROUTER_HOST": "10.0.0.9", "ENTRY_NAME": "MyNAS",
                       "SOURCE": "router", "WRITE_ALL": False,
                       "MAX_ADDRS": 2, "IFACE": "eth0"}, f)
        ov = st_mod.load_overlay(path)
        # 已删的项被忽略；ENTRY_NAME 则迁移成 RULES，用户的配置不能丢
        self.assertEqual(ov.get("ROUTER_HOST"), "10.0.0.9")
        self.assertNotIn("SOURCE", ov)
        self.assertNotIn("WRITE_ALL", ov)
        self.assertNotIn("MAX_ADDRS", ov)
        self.assertNotIn("IFACE", ov)
        self.assertEqual(ov["RULES"], [{"name": "MyNAS", "mac": "",
                                        "port": "-1", "remote_ip": "::/0"}])
        cfg = Config(rules=[Rule(name="NAS")])
        st_mod.apply_overlay(cfg, ov)
        self.assertEqual(cfg.host, "10.0.0.9")
        self.assertEqual(cfg.rules[0].name, "MyNAS")

    def test_web_submit_still_rejects_unknown_key(self):
        """但网页提交这条路径必须继续严格报错：
        把用户提交的设置静默丢掉，是最坏的行为。"""
        from app import settings as st_mod
        with self.assertRaises(st_mod.SettingsError) as cm:
            st_mod.validate_overlay({"SOURCE": "router"})
        self.assertIn("SOURCE", str(cm.exception))

    def test_page_exposes_only_the_fixed_flow(self):
        """页面上不该再出现取址开关与旧条目表单 —— 规则统一在白名单页管理。"""
        from app import settings as st_mod
        keys = {f["key"] for g in st_mod.view(Config(), {})
                for f in g["fields"]}
        for gone in ("SOURCE", "MISMATCH_POLICY", "WRITE_ALL", "MAX_ADDRS",
                     "ADDR_SUFFIX", "IFACE", "TARGET_HOSTNAME", "ALLOW_ULA",
                     "TARGET_MAC", "ENTRY_NAME", "PORT", "REMOTE_IP"):
            self.assertNotIn(gone, keys)
        for kept in ("ROUTER_HOST", "ROUTER_PASSWORD", "POLL_INTERVAL",
                     "DRY_RUN", "LOG_LEVEL"):
            self.assertIn(kept, keys)

    def test_rules_json(self):
        from app.config import load_rules_from_env
        raw = ('[{"name":"NAS","port":16669,"mac":"00:11:22:33:44:55"},'
               '{"name":"NVR","port":8000,"mac":"AA:BB:CC:DD:EE:FF"}]')
        saved = os.environ.get("RULES")
        os.environ["RULES"] = raw
        try:
            rules = load_rules_from_env()
            self.assertEqual([r.name for r in rules], ["NAS", "NVR"])
            self.assertEqual(rules[1].port, 8000)
        finally:
            if saved is None:
                os.environ.pop("RULES", None)
            else:
                os.environ["RULES"] = saved

    def test_missing_password_exits_only_for_once_mode(self):
        from app.config import load_config
        saved = os.environ.get("ROUTER_PASSWORD")
        os.environ.pop("ROUTER_PASSWORD", None)
        try:
            # 常驻模式：没密码也允许启动（纯网页首次配置的前提）
            load_config([])
            # --once 单次模式：没有凭据必然一事无成，必须干净报错
            with self.assertRaises(SystemExit):
                load_config(["--once"])
        finally:
            if saved is not None:
                os.environ["ROUTER_PASSWORD"] = saved


class FakeRouterLoggedOut(FakeRouter):
    """未登录、也没有可用会话的假路由器：测「等用户填密码」那条路径。"""

    def __init__(self, **kw):
        super().__init__(**kw)
        self.logged_in = False

    def check_session(self):
        return False


class TestCounters(unittest.TestCase):
    """累计写入计数：跨容器重启保留、坏文件不致命。

    现场问题：容器重启一次计数就归零，网页上「累计写入」永远停在个位数，
    用户没法判断程序到底同步过没有。
    """

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="ipv6sync-counters-")
        self.path = os.path.join(self.dir, "state.json")

    def test_accumulates_and_survives_restart(self):
        from app import state as st
        c = st.Counters(self.path)
        self.assertEqual(c.total_writes, 0)
        c.bump(created=1)
        c.bump(updated=2)
        self.assertEqual(c.total_writes, 3)
        self.assertEqual(c.session_writes, 3)
        self.assertTrue(c.first_write_at and c.last_write_at)
        self.assertTrue(c.flush())

        # 「重启」= 新进程读同一个文件
        c2 = st.Counters(self.path)
        self.assertEqual((c2.created, c2.updated), (1, 2))
        self.assertEqual(c2.total_writes, 3)
        self.assertEqual(c2.session_writes, 0)     # 本次启动从 0 起算

    def test_removed_counted_separately(self):
        """删条目也是真的改了设备配置，要计数，但不算进「写入」。"""
        from app import state as st
        c = st.Counters(self.path)
        c.bump(removed=2)
        c.flush()
        self.assertEqual(c.removed, 2)
        self.assertEqual(c.total_writes, 0)
        self.assertEqual(st.Counters(self.path).removed, 2)

    def test_reset_zeroes_everything_and_persists(self):
        """网页「重置累计写入」：清零要落盘，重启后不会从旧文件里复活。"""
        from app import state as st
        c = st.Counters(self.path)
        c.bump(created=5, removed=3)
        c.flush()
        c.reset()
        self.assertEqual(c.total_writes, 0)
        self.assertEqual(c.removed, 0)
        self.assertEqual(c.session_writes, 0)
        self.assertFalse(c.first_write_at and c.last_write_at)
        self.assertTrue(c.flush())
        c2 = st.Counters(self.path)
        self.assertEqual(c2.total_writes, 0)
        self.assertEqual(c2.removed, 0)

    def test_bump_nothing_is_noop(self):
        from app import state as st
        c = st.Counters(self.path)
        c.bump()
        self.assertFalse(c._dirty)
        self.assertFalse(os.path.exists(self.path))

    def test_corrupt_file_falls_back_to_zero(self):
        """状态文件坏了只是「从 0 开始」，绝不能让同步起不来。"""
        from app import state as st
        with open(self.path, "w", encoding="utf-8") as f:
            f.write("{ 这不是 json")
        c = st.Counters(self.path)
        self.assertEqual(c.total_writes, 0)
        self.assertIsNotNone(c.file_error)
        c.bump(created=1)
        self.assertTrue(c.flush())                 # 写回去就把坏文件修好了
        self.assertIsNone(c.file_error)
        self.assertEqual(st.Counters(self.path).total_writes, 1)

    def test_bad_field_values_ignored(self):
        import json
        from app import state as st
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump([1, 2, 3], f)                # 顶层不是对象
        self.assertEqual(st.Counters(self.path).total_writes, 0)

        with open(self.path, "w", encoding="utf-8") as f:
            json.dump({"created": -5, "updated": True, "removed": 2}, f)
        c = st.Counters(self.path)
        self.assertEqual((c.created, c.updated, c.removed), (0, 0, 2))

    def test_unwritable_target_only_warns(self):
        """落盘失败不能抛异常，也不能清 dirty —— 下轮还要再试。"""
        from app import state as st
        blocker = os.path.join(self.dir, "blocker")
        with open(blocker, "w", encoding="utf-8") as f:
            f.write("x")                            # 路径中间挡着一个文件
        c = st.Counters(os.path.join(blocker, "state.json"))
        c.bump(created=1)
        self.assertFalse(c.flush())
        self.assertTrue(c._dirty)
        self.assertIsNotNone(c.file_error)


class TestStatusSnapshot(LocalNetStub, unittest.TestCase):
    """网页状态里的 ok 必须能反映「最近一轮」。

    现场问题：网页是**轮询**取状态的，永远赶不上某一轮；snapshot() 不传 ok
    时以前返回 None，前端 `!!st.ok` 恒为 false —— 于是「同步」一直显示
    「等待首轮」，哪怕它每分钟都在正常写入。
    """

    def test_never_ran_is_none(self):
        s = Syncer(make_cfg(), FakeRouter(entries=[]))
        snap = s.snapshot()
        self.assertIsNone(snap["ok"])
        self.assertEqual(snap["last_tick_at"], "")
        self.assertEqual(snap["last_success_at"], "")

    def test_polling_after_success_keeps_reporting_ok(self):
        s = Syncer(make_cfg(), FakeRouter(entries=[]))
        s.tick()
        for _ in range(3):                          # 轮询多次结果都要稳定
            snap = s.snapshot()
            self.assertTrue(snap["ok"])
            self.assertTrue(snap["last_success_at"])
            self.assertEqual(snap["consecutive_failures"], 0)

    def test_unconfigured_password_is_false_not_none(self):
        """没填密码 = 「等配置」，不是「还没跑过」—— 这两者前端文案不同。"""
        s = Syncer(make_cfg(password=""), FakeRouterLoggedOut(entries=[]))
        self.assertFalse(s.tick()["ok"])
        snap = s.snapshot()
        self.assertIs(snap["ok"], False)            # 轮询不能又变回 None
        self.assertTrue(snap["unconfigured"])
        self.assertEqual(snap["consecutive_failures"], 0)   # 等配置不算失败

    def test_tick_flushes_counters(self):
        """一轮结束就落盘：容器随时可能被重启，计数不能只留在内存里。"""
        cfg = make_cfg()
        s = Syncer(cfg, FakeRouter(entries=[]))
        s.tick()
        self.assertEqual(s.total_writes, 1)
        self.assertTrue(os.path.exists(cfg.state_file), "tick 结束应已落盘")

        s2 = Syncer(cfg, FakeRouter(entries=[]))    # 模拟重启
        self.assertEqual(s2.total_writes, 1)
        self.assertEqual(s2.counters.session_writes, 0)

    def test_stale_removal_counted_without_inflating_writes(self):
        """地址变少要删旧条目：删要计数（改了设备），但不能算成「写入」。"""
        cfg = make_cfg()
        stale = {"Name": "NAS@2", "LocalIp": THIRD_ADDR, "RemoteIp": "::/0",
                 "Port": -1, "ID": "9"}
        s = Syncer(cfg, FakeRouter(entries=[stale]))
        s.tick()
        self.assertEqual(s.counters.removed, 1)
        self.assertEqual(s.total_writes, 1)         # 只算了新建的那 1 条


class TestEvents(unittest.TestCase):
    """修改日志：文件即数据 —— 追加/读取/裁剪/清空，坏行跳过不致命。"""

    def setUp(self):
        import tempfile
        self.dir = tempfile.mkdtemp(prefix="evtest-")
        self.state = os.path.join(self.dir, "state.json")

    def test_record_and_read_roundtrip(self):
        from app import events
        events.record(self.state, {"device": "NAS", "action": "created",
                                   "entry": "NAS", "addr": "240e::1"}, 100)
        events.record(self.state, {"device": "NAS", "action": "removed",
                                   "entry": "NAS@2", "addr": "240e::2"}, 100)
        got = events.read(self.state)
        self.assertEqual([g["action"] for g in got], ["created", "removed"])
        self.assertTrue(all(g.get("ts") for g in got))   # 落盘时补了时间戳

    def test_trim_keeps_latest(self):
        from app import events
        for i in range(7):
            events.record(self.state, {"device": "d", "addr": f"240e::{i}"}, 5)
        got = events.read(self.state)
        self.assertEqual(len(got), 5)
        self.assertEqual(got[0]["addr"], "240e::2")       # 最旧的两条被丢
        self.assertEqual(got[-1]["addr"], "240e::6")

    def test_clear_and_corrupt_line_skipped(self):
        from app import events
        events.record(self.state, {"device": "d"}, 100)
        # 手工塞进半行（模拟掉电残留）
        with open(events.events_path(self.state), "a", encoding="utf-8") as f:
            f.write('{"device": "broken"')
        got = events.read(self.state)
        self.assertEqual(len(got), 1)
        events.clear(self.state)
        self.assertEqual(events.read(self.state), [])

    def test_sync_writes_events_on_change(self):
        """同步引擎真实写入时必须留下修改日志（含更新的旧地址）。"""
        from app import events
        r = FakeRouter(entries=[])
        cfg = make_cfg()
        self.patch_local([OLD_ADDR])
        s = Syncer(cfg, r)
        s.trigger = "手动同步"
        s.tick()
        got = events.read(cfg.state_file)
        self.assertTrue(got)
        ev = [g for g in got if g.get("device") == "NAS"]
        self.assertTrue(ev)
        self.assertEqual(ev[0]["action"], "created")
        self.assertEqual(ev[0]["trigger"], "手动同步")

    def patch_local(self, addrs, macs=None, temp=None):
        """与 TestSyncer.patch_local 相同的「网卡上有什么」改写。"""
        discover.local_candidates = (
            lambda: [discover.canon(a) or a for a in addrs])
        discover.temporary_set = lambda: set(temp or ())
        if macs is not None:
            discover.local_macs = lambda: set(macs)


class TestWakeOnLan(unittest.TestCase):
    """网络唤醒：魔术包字节、广播地址推导、限频、以及 Node 侧的准入判断。"""

    def test_magic_packet_bytes(self):
        pkt = wol.magic_packet("3C:7C:3F:11:22:33")
        self.assertEqual(len(pkt), 102)
        self.assertEqual(pkt[:6], b"\xff" * 6)
        mac = bytes.fromhex("3c7c3f112233")
        for i in range(16):
            off = 6 + i * 6
            self.assertEqual(pkt[off:off + 6], mac, f"第 {i + 1} 遍 MAC 不对")

    def test_mac_writing_styles_all_accepted(self):
        want = wol.magic_packet("3C:7C:3F:11:22:33")
        for style in ("3c:7c:3f:11:22:33", "3C-7C-3F-11-22-33",
                      "3c7c3f112233", " 3C:7C:3F:11:22:33 ", "3C7C.3F11.2233"):
            self.assertEqual(wol.magic_packet(style), want, style)

    def test_bad_mac_rejected(self):
        for bad in ("", "3C:7C:3F", "zz:zz:zz:zz:zz:zz", "3C:7C:3F:11:22"):
            with self.assertRaises(ValueError, msg=bad):
                wol.magic_packet(bad)

    def test_broadcast_from_route_table(self):
        """/24 直连路由 → 该网段的定向广播，且始终附带全局广播。"""
        routes = [(0xC0A80300, 0xFFFFFF00)]      # 192.168.3.0/24
        with mock.patch.object(wol, "_routes", return_value=routes):
            got = wol.broadcast_targets("192.168.3.117")
        self.assertEqual(got, ["192.168.3.255", "255.255.255.255"])

    def test_broadcast_respects_non_24_prefix(self):
        """/16 网段不能按 /24 猜，要按路由表算。"""
        routes = [(0xC0A80000, 0xFFFF0000)]      # 192.168.0.0/16
        with mock.patch.object(wol, "_routes", return_value=routes):
            got = wol.broadcast_targets("192.168.3.117")
        self.assertIn("192.168.255.255", got)
        self.assertNotIn("192.168.3.255", got)

    def test_broadcast_falls_back_to_24(self):
        """路由表读不到（非 Linux / 容器没挂 proc）时退回按 /24 猜。"""
        with mock.patch.object(wol, "_routes", return_value=[]):
            got = wol.broadcast_targets("10.4.7.9")
        self.assertEqual(got, ["10.4.7.255", "255.255.255.255"])

    def test_broadcast_without_ipv4(self):
        """设备没有 IPv4（纯 IPv6 / 空字段）时只能发全局广播。"""
        for empty in ("", None, "fe80::1"):
            got = wol.broadcast_targets(empty)
            self.assertEqual(got, ["255.255.255.255"], empty)

    def test_send_counts_packets(self):
        sent = []

        class FakeSock:
            def __init__(self, *a, **k):
                pass

            def setsockopt(self, *a):
                pass

            def sendto(self, pkt, addr):
                sent.append((len(pkt), addr))

            def close(self):
                pass

        with mock.patch.object(wol.socket, "socket", FakeSock), \
                mock.patch.object(wol, "ROUND_GAP", 0), \
                mock.patch.object(wol, "_routes", return_value=[]):
            res = wol.send("3C:7C:3F:11:22:33", "192.168.3.117")
        self.assertTrue(res["ok"])
        # 2 个目标 × 2 个端口 × 3 轮
        self.assertEqual(res["sent"], 12)
        self.assertEqual(len(sent), 12)
        self.assertTrue(all(n == 102 for n, _ in sent))
        self.assertEqual({a[1] for _, a in sent}, {9, 7})

    def test_throttle(self):
        gate = wol.Throttle(cooldown=10.0)
        self.assertEqual(gate.acquire("aa", now=1000.0), 0.0)
        self.assertGreater(gate.acquire("aa", now=1005.0), 0.0)   # 冷却中
        self.assertEqual(gate.acquire("aa", now=1010.5), 0.0)    # 冷却过了
        self.assertEqual(gate.acquire("bb", now=1011.0), 0.0)    # 别的设备不受影响

    def test_throttle_global_quota(self):
        gate = wol.Throttle(cooldown=1.0, window=30.0, quota=3)
        for i in range(3):
            self.assertEqual(gate.acquire(f"m{i}", now=100.0 + i), 0.0)
        self.assertGreater(gate.acquire("m9", now=104.0), 0.0)    # 超额
        self.assertEqual(gate.acquire("m9", now=131.0), 0.0)     # 窗口滑过去了


class TestWakeAdmission(unittest.TestCase):
    """Node.wake_device 的准入：只唤醒设备档案里出现过的 MAC。"""

    def make_node(self, router):
        cfg = Config(rules=[])
        node = object.__new__(Node)      # 绕开 __init__：不建真路由器、不读会话
        node.cfg = cfg
        node.router = router
        node.syncer = Syncer(cfg, router)
        node._lock = threading.RLock()
        node._wol_gate = wol.Throttle(cooldown=10.0)
        return node

    def test_unknown_mac_rejected(self):
        node = self.make_node(FakeRouter())
        with mock.patch.object(wol, "send") as send:
            res = node.wake_device({"mac": "AA:BB:CC:DD:EE:99"})
        self.assertFalse(res["ok"])
        self.assertIn("不在路由器设备档案", res["error"])
        send.assert_not_called()

    def test_known_mac_sends(self):
        node = self.make_node(FakeRouter())
        with mock.patch.object(wol, "send",
                               return_value={"ok": True, "sent": 12,
                                             "targets": ["255.255.255.255"]}) as send:
            res = node.wake_device({"mac": NAS_MAC})
        self.assertTrue(res["ok"])
        send.assert_called_once()
        self.assertEqual(send.call_args[0][0], NAS_MAC)      # 用档案里的原始写法
        self.assertEqual(send.call_args[0][1], "192.168.3.5")  # 带上 IPv4 算广播

    def test_second_click_throttled(self):
        node = self.make_node(FakeRouter())
        with mock.patch.object(wol, "send",
                               return_value={"ok": True, "sent": 12, "targets": []}):
            self.assertTrue(node.wake_device({"mac": NAS_MAC})["ok"])
            again = node.wake_device({"mac": NAS_MAC})
        self.assertFalse(again["ok"])
        self.assertTrue(again["throttled"])

    def test_bad_mac_rejected_before_router(self):
        """MAC 明显不合法时不该去碰路由器（这是网页侧的低级误输入）。"""
        node = self.make_node(FakeRouter())
        with self.assertRaises(SettingsError):
            node.wake_device({"mac": "nope"})


class FakeActionRouter:
    """只实现计划任务用到的四个动作接口，并记录每次请求的原始形态。"""

    def __init__(self, power=1, wan_id="InternetConnection_1"):
        self.power = power
        self.wan_id = wan_id
        self.posts = []
        self.gets = []
        self.rebooted = False

    def get(self, name, params=None):
        self.gets.append(name)
        if name == "wlanradio":
            return {"Enable2G": True, "Enable5G": True, "InitEnable2G": True,
                    "InitEnable5G": True, "PowerMode": self.power,
                    "PowerModeChgTip": 0, "WLANMode": 1}
        if name == "channelinfo":
            return {"ChannelDeploy": 1, "NetChannelMode": 3}
        if name == "wan":
            if not self.wan_id:
                return {"wanTypeActivecontrol": {}}
            return {"wanTypeActivecontrol": {"ID": self.wan_id}}
        raise AssertionError(f"假路由器没实现 GET {name}")

    def post(self, name, data=None, wrapped=True, action=None):
        self.posts.append({"name": name, "data": data,
                           "action": action, "wrapped": wrapped})
        if name == "service/reboot.cgi":
            self.rebooted = True
            return {}
        if name in ("wan", "ntwk/wan"):
            return {}
        if name in ("wlanradio", "ntwk/wlanradio"):
            self.power = int((data or {}).get("PowerMode", self.power))
            return {}
        if name in ("channelinfo", "ntwk/channelinfo"):
            return {}
        raise AssertionError(f"假路由器没实现 POST {name}")


class FlipFlopRouter(FakeActionRouter):
    """最小写被忽略的固件：第一次 wlanradio POST 不动档位，整包写才生效。"""

    def __init__(self, power=1):
        super().__init__(power=power)
        self.n = 0

    def post(self, name, data=None, wrapped=True, action=None):
        self.posts.append({"name": name, "data": data,
                           "action": action, "wrapped": wrapped})
        if name in ("wlanradio", "ntwk/wlanradio"):
            self.n += 1
            if self.n > 1:                       # 只有第二次（整包）才认
                self.power = int((data or {}).get("PowerMode", self.power))
            return {}
        return {}


def _epoch(y, mo, d, h, mi):
    return time.mktime((y, mo, d, h, mi, 0, 0, 0, -1))


class TestTaskTime(unittest.TestCase):
    """到点判定：这是整块功能里唯一容易算错的地方。"""

    def test_parse_at(self):
        self.assertEqual(tk.parse_at("04:30"), (4, 30))
        self.assertEqual(tk.parse_at("4:05"), (4, 5))
        self.assertEqual(tk.parse_at("23:59"), (23, 59))
        for bad in ("24:00", "12:60", "0430", "", None, "ab:cd"):
            with self.assertRaises(ValueError, msg=str(bad)):
                tk.parse_at(bad)

    def test_last_slot_daily(self):
        now = _epoch(2026, 10, 24, 4, 31)
        task = {"at": "04:30", "days": [1, 2, 3, 4, 5, 6, 7]}
        slot = tk.last_slot(task, now)
        self.assertEqual(slot, _epoch(2026, 10, 24, 4, 30))

    def test_last_slot_before_todays_point_rolls_back(self):
        """今天还没到 04:30 时，最近一个计划点是昨天的。"""
        now = _epoch(2026, 10, 24, 3, 0)
        task = {"at": "04:30", "days": [1, 2, 3, 4, 5, 6, 7]}
        self.assertEqual(tk.last_slot(task, now), _epoch(2026, 10, 23, 4, 30))

    def test_last_slot_weekday_filter(self):
        """2026-10-24 是周六。只在周一执行的任务：最近计划点是 10-19。"""
        now = _epoch(2026, 10, 24, 12, 0)
        task = {"at": "04:30", "days": [1]}
        slot = tk.last_slot(task, now)
        self.assertEqual(time.localtime(slot).tm_wday, 0)        # 周一
        self.assertEqual(slot, _epoch(2026, 10, 19, 4, 30))

    def test_next_slot(self):
        now = _epoch(2026, 10, 24, 4, 31)
        task = {"at": "04:30", "days": [1, 2, 3, 4, 5, 6, 7]}
        self.assertEqual(tk.next_slot(task, now), _epoch(2026, 10, 25, 4, 30))

    def test_due_inside_window(self):
        now = _epoch(2026, 10, 24, 4, 32)
        task = {"at": "04:30", "days": [1, 2, 3, 4, 5, 6, 7], "enabled": True}
        self.assertIsNotNone(tk.due_slot(task, now))

    def test_due_outside_window_not_fired(self):
        """过了窗口就不补跑 —— 否则容器晚起两小时会突然重启一次路由器。"""
        now = _epoch(2026, 10, 24, 6, 0)
        task = {"at": "04:30", "days": [1, 2, 3, 4, 5, 6, 7], "enabled": True}
        self.assertIsNone(tk.due_slot(task, now))

    def test_due_skipped_when_already_fired(self):
        slot = _epoch(2026, 10, 24, 4, 30)
        now = _epoch(2026, 10, 24, 4, 31)
        task = {"at": "04:30", "days": [1, 2, 3, 4, 5, 6, 7],
                "enabled": True, "last_slot": slot}
        self.assertIsNone(tk.due_slot(task, now))

    def test_disabled_never_due(self):
        now = _epoch(2026, 10, 24, 4, 31)
        task = {"at": "04:30", "days": [1, 2, 3, 4, 5, 6, 7], "enabled": False}
        self.assertIsNone(tk.due_slot(task, now))

    def test_describe(self):
        self.assertEqual(tk.describe({"at": "04:30", "days": [1, 2, 3, 4, 5, 6, 7]}),
                         "每天 04:30")
        self.assertEqual(tk.describe({"at": "04:30", "days": [1]}), "每周一 04:30")
        self.assertEqual(tk.describe({"at": "23:00", "days": [1, 4]}),
                         "每周一、四 23:00")
        self.assertEqual(
            tk.describe({"at": "22:00", "days": [1, 2, 3, 4, 5, 6, 7],
                         "kind": "wifi_power", "params": {"power_mode": 0}}),
            "每天 22:00 → 睡眠")


class TestTaskModel(unittest.TestCase):
    def test_clean_defaults(self):
        t = tk.clean_task({"kind": "reboot", "at": "4:05"})
        self.assertEqual(t["at"], "04:05")
        self.assertEqual(t["days"], [1, 2, 3, 4, 5, 6, 7])
        self.assertEqual(t["name"], "重启路由器")
        self.assertTrue(t["enabled"])
        self.assertTrue(t["id"].startswith("t"))

    def test_clean_rejects(self):
        for bad in ({"kind": "nope", "at": "04:30"},
                    {"kind": "reboot", "at": "25:00"},
                    {"kind": "wifi_power", "at": "04:30"},
                    {"kind": "wifi_power", "at": "04:30",
                     "params": {"power_mode": 9}}):
            with self.assertRaises(ValueError, msg=str(bad)):
                tk.clean_task(bad)

    def test_clean_days_normalized(self):
        t = tk.clean_task({"kind": "reboot", "at": "04:30",
                           "days": [7, 3, 3, 0, 9]})
        self.assertEqual(t["days"], [3, 7])

    def test_name_too_long(self):
        with self.assertRaises(ValueError):
            tk.clean_task({"kind": "reboot", "at": "04:30", "name": "x" * 31})

    def test_roundtrip_persistence(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "tasks.json")
            a = tk.Tasks(lambda: FakeActionRouter(), path)
            a.upsert({"kind": "reboot", "at": "04:30", "name": "每晚重启"})
            a.upsert({"kind": "wifi_power", "at": "22:00",
                      "params": {"power_mode": 0}})
            b = tk.Tasks(lambda: FakeActionRouter(), path)
            view = b.view()
            self.assertEqual(len(view["tasks"]), 2)
            self.assertEqual(view["tasks"][0]["when"], "每天 04:30")
            self.assertEqual(view["tasks"][1]["kind_label"], "Wi-Fi 功率模式")

    def test_delete_and_toggle(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "tasks.json")
            s = tk.Tasks(lambda: FakeActionRouter(), path)
            tid = s.upsert({"kind": "reboot", "at": "04:30"})["task"]["id"]
            self.assertFalse(s.toggle(tid, False)["enabled"])
            self.assertFalse(s.view()["tasks"][0]["enabled"])
            s.delete(tid)
            self.assertEqual(s.view()["tasks"], [])
            with self.assertRaises(ValueError):
                s.delete(tid)


class TestTaskApply(unittest.TestCase):
    """四个动作的请求形态 —— 全部逆向自固件前端，错了就是 400。"""

    def test_reboot_payload_has_no_data_key(self):
        r = FakeActionRouter()
        res = tk.apply(r, {"kind": "reboot"})
        self.assertTrue(res["ok"])
        self.assertEqual(len(r.posts), 1)
        p = r.posts[0]
        self.assertEqual(p["name"], "service/reboot.cgi")
        self.assertFalse(p["wrapped"])          # → body 里连 data 键都没有
        self.assertEqual(p["data"], {})
        self.assertTrue(r.rebooted)

    def test_redial_reads_wan_id_first(self):
        r = FakeActionRouter(wan_id="InternetConnection_3")
        res = tk.apply(r, {"kind": "redial"})
        self.assertTrue(res["ok"])
        self.assertEqual(r.gets, ["wan"])
        p = r.posts[0]
        self.assertEqual(p["name"], "wan")
        self.assertEqual(p["action"], "reconnect")
        self.assertEqual(p["data"], {"Path": "InternetConnection_3"})

    def test_redial_without_wan_id_refuses(self):
        """Path 写死会失效，取不到就别发 —— 发一个空 Path 只会拿到错误码。"""
        r = FakeActionRouter(wan_id="")
        res = tk.apply(r, {"kind": "redial"})
        self.assertFalse(res["ok"])
        self.assertIn("WAN", res["msg"])
        self.assertEqual(r.posts, [])

    def test_wifi_power_minimal_write(self):
        r = FakeActionRouter(power=1)
        res = tk.apply(r, {"kind": "wifi_power", "params": {"power_mode": 2}})
        self.assertTrue(res["ok"])
        self.assertEqual(r.posts[0]["data"], {"PowerMode": 2})   # 只发这一个字段
        self.assertEqual(r.power, 2)

    def test_wifi_power_skips_when_already_there(self):
        r = FakeActionRouter(power=1)
        res = tk.apply(r, {"kind": "wifi_power", "params": {"power_mode": 1}})
        self.assertTrue(res["ok"])
        self.assertTrue(res.get("skipped"))
        self.assertEqual(r.posts, [])           # 值没变就不写，少一次写操作

    def test_wifi_power_falls_back_to_full_object(self):
        r = FlipFlopRouter(power=1)
        res = tk.apply(r, {"kind": "wifi_power", "params": {"power_mode": 0}})
        self.assertTrue(res["ok"])
        self.assertEqual(len(r.posts), 2)
        full = r.posts[1]["data"]
        self.assertEqual(full["PowerMode"], 0)
        # 完整写回时带上读到的全部 7 个字段（实测不含 SSID / 密码）
        for k in ("Enable2G", "Enable5G", "InitEnable2G", "InitEnable5G",
                  "PowerModeChgTip", "WLANMode"):
            self.assertIn(k, full)

    def test_wifi_power_reports_failure(self):
        class Dead(FakeActionRouter):
            def post(self, name, data=None, wrapped=True, action=None):
                self.posts.append({"name": name, "data": data,
                                   "action": action, "wrapped": wrapped})
                return {}                       # 永远不认

        r = Dead(power=1)
        res = tk.apply(r, {"kind": "wifi_power", "params": {"power_mode": 2}})
        self.assertFalse(res["ok"])
        self.assertIn("没生效", res["msg"])

    def test_channel_reuses_current_values(self):
        """一键优化的 body 是「当前值 + action=UpdateAll」，不是写死 1 / 1。"""
        r = FakeActionRouter()
        res = tk.apply(r, {"kind": "channel"})
        self.assertTrue(res["ok"])
        self.assertEqual(r.posts[0]["name"], "channelinfo")
        self.assertEqual(r.posts[0]["data"],
                         {"action": "UpdateAll", "ChannelDeploy": 1,
                          "NetChannelMode": 3})

    def test_find_wan_id_fallbacks(self):
        self.assertEqual(tk.find_wan_id({"wanTypeActivecontrol": {"ID": "InternetConnection_1"}}),
                         "InternetConnection_1")
        # 大小写不一致的固件
        self.assertEqual(tk.find_wan_id({"WanTypeActivecontrol": {"Id": "InternetConnection_2"}}),
                         "InternetConnection_2")
        # 藏在列表里
        self.assertEqual(tk.find_wan_id({"x": [{"y": {"id": "InternetConnection_7"}}]}),
                         "InternetConnection_7")
        self.assertEqual(tk.find_wan_id({"nothing": 1}), "")


class TestTaskScheduler(unittest.TestCase):
    def make(self, d, router=None):
        router = router or FakeActionRouter()
        return tk.Tasks(lambda: router, os.path.join(d, "tasks.json")), router

    def test_tick_fires_once_and_records(self):
        with tempfile.TemporaryDirectory() as d:
            s, r = self.make(d)
            s.upsert({"kind": "reboot", "at": "04:30"})
            now = _epoch(2026, 10, 24, 4, 30)
            res = s.tick(now)
            self.assertTrue(res["ok"])
            self.assertTrue(r.rebooted)
            # 同一分钟再心跳一次：不能重复执行
            self.assertIsNone(s.tick(now + 5))

    def test_quiet_period_blocks_next_fire(self):
        with tempfile.TemporaryDirectory() as d:
            s, r = self.make(d)
            s.upsert({"kind": "reboot", "at": "04:30"})
            now = _epoch(2026, 10, 24, 4, 30)
            s.tick(now)
            self.assertGreater(s.quiet_left(), 0)
            self.assertIsNone(s.tick(now + 30))      # 静默期内什么都不做

    def test_quiet_persists_across_restart(self):
        """容器恰好在这时重启，静默期也要继续生效，否则会立刻再触发一次。"""
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "tasks.json")
            s1 = tk.Tasks(lambda: FakeActionRouter(), path)
            s1.upsert({"kind": "reboot", "at": "04:30"})
            s1.tick(_epoch(2026, 10, 24, 4, 30))
            s2 = tk.Tasks(lambda: FakeActionRouter(), path)
            self.assertGreater(s2.quiet_left(), 0)

    def test_only_one_task_per_slot(self):
        with tempfile.TemporaryDirectory() as d:
            s, r = self.make(d)
            s.upsert({"kind": "reboot", "at": "04:30", "name": "A"})
            s.upsert({"kind": "channel", "at": "04:30", "name": "B"})
            now = _epoch(2026, 10, 24, 4, 30)
            s.tick(now)
            self.assertEqual(len(r.posts), 1)        # 只跑了一个
            msgs = [t["last_msg"] for t in s.view()["tasks"]]
            self.assertTrue(any("跳过" in m for m in msgs), msgs)

    def test_mark_missed_does_not_backfill(self):
        with tempfile.TemporaryDirectory() as d:
            s, r = self.make(d)
            s.upsert({"kind": "reboot", "at": "04:30"})
            missed = s.mark_missed(_epoch(2026, 10, 24, 9, 0))
            self.assertEqual(missed, ["重启路由器"])
            self.assertFalse(r.rebooted)             # 没真去重启
            self.assertIsNone(s.tick(_epoch(2026, 10, 24, 9, 1)))

    def test_disabled_task_not_fired(self):
        with tempfile.TemporaryDirectory() as d:
            s, r = self.make(d)
            tid = s.upsert({"kind": "reboot", "at": "04:30"})["task"]["id"]
            s.toggle(tid, False)
            self.assertIsNone(s.tick(_epoch(2026, 10, 24, 4, 30)))
            self.assertFalse(r.rebooted)

    def test_manual_run_ignores_window(self):
        with tempfile.TemporaryDirectory() as d:
            s, r = self.make(d)
            tid = s.upsert({"kind": "channel", "at": "04:30"})["task"]["id"]
            res = s.run(tid, manual=True)            # 什么时间点都能手动跑
            self.assertTrue(res["ok"])
            self.assertEqual(len(r.posts), 1)

    def test_failure_is_recorded_and_not_retried(self):
        with tempfile.TemporaryDirectory() as d:
            class Boom(FakeActionRouter):
                def post(self, *a, **k):
                    raise RuntimeError("路由器掉线")
            s = tk.Tasks(lambda: Boom(), os.path.join(d, "tasks.json"))
            s.upsert({"kind": "reboot", "at": "04:30"})
            now = _epoch(2026, 10, 24, 4, 30)
            res = s.tick(now)
            self.assertFalse(res["ok"])
            task = s.view()["tasks"][0]
            self.assertFalse(task["last_ok"])
            self.assertIn("路由器掉线", task["last_msg"])
            self.assertIsNone(s.tick(now + 5))       # 失败也不重试

    def test_write_before_send(self):
        """先落盘再发请求：发送瞬间被 kill 也不会重复触发。"""
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "tasks.json")
            seen = {}

            class Check(FakeActionRouter):
                def post(self, *a, **k):
                    with open(path, encoding="utf-8") as f:
                        seen["hit"] = json.load(f)["tasks"][0]["last_slot"]
                    return {}

            s = tk.Tasks(lambda: Check(), path)
            s.upsert({"kind": "reboot", "at": "04:30"})
            now = _epoch(2026, 10, 24, 4, 30)
            s.tick(now)
            self.assertEqual(seen["hit"], now)

    def test_bad_file_is_tolerated(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "tasks.json")
            with open(path, "w", encoding="utf-8") as f:
                f.write("{ 这不是 json")
            s = tk.Tasks(lambda: FakeActionRouter(), path)
            self.assertEqual(s.view()["tasks"], [])
            s.upsert({"kind": "reboot", "at": "04:30"})   # 还能正常用
            self.assertEqual(len(s.view()["tasks"]), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
