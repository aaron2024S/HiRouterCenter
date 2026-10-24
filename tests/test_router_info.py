# -*- coding: utf-8 -*-
"""router_info.collect 的取数规则。

核心是三件容易翻车的事：
  · WAN IPv6 不能把 DNS / 前缀当地址（它们也是全球单播）；
  · 双频合一（2.4G / 5G 同名）要合并显示；
  · 信道只认「数值在信道范围内」的键，ChannelDeploy / NetChannelMode 不能误判。
"""
import unittest

from app import router_info


class FakeRouter:
    """按路径返回预置数据，没配的直接抛错（模拟 404 / 登录失败）。"""

    def __init__(self, data=None):
        self.data = data or {}

    def get(self, name, params=None):
        if name not in self.data:
            raise RuntimeError("404")
        return self.data[name]


DEVICEINFO = {
    "FriendlyName": "华为凌霄子母路由 Q7 网线版",
    "HardwareVersion": "VER.A",
    "SoftwareVersion": "6.1.0.20(V7R2)",
    "HarmonyOSVersion": "6.1.0",
    "UpTime": 3 * 86400 + 4 * 3600 + 14 * 60,
    "WANMACAddress": "40:06:34:65:84:22",
    "LANMACAddress": "40:06:34:65:84:22",
}


class Wan6Test(unittest.TestCase):
    """WAN IPv6 的取数：DNS 和前缀都不能算地址。"""

    def test_skips_dns_and_prefix(self):
        r = FakeRouter({
            "deviceinfo": dict(DEVICEINFO),
            "ipv6_wan": {
                "DefaultGateway": "fe80::200:5eff:fe00:108",
                "DnsServer": "240e:5a::6666",
                "DnsServer2": "240e:5b::6666",
                "Prefix": "240e:3a5:4801:1600::/64",
                "WanIpAddress": "240e:3a0:483c:e239:2c4f:9fdb:e3ea:edc7/64",
            },
        })
        out = router_info.collect(r)
        self.assertEqual(out["wan6"], "240e:3a0:483c:e239:2c4f:9fdb:e3ea:edc7")

    def test_prefers_key_named_value(self):
        r = FakeRouter({
            "deviceinfo": dict(DEVICEINFO),
            "ipv6_wan": {"DnsServer": "240e:5a::6666",
                         "WanIPv6": "240e:3a0:483c:e239:2c4f:9fdb:e3ea:edc7"},
        })
        out = router_info.collect(r)
        self.assertEqual(out["wan6"], "240e:3a0:483c:e239:2c4f:9fdb:e3ea:edc7")

    def test_compressed_address_never_taken_as_wan6(self):
        # 返回体里只有压缩形式（DNS / 前缀）→ 宁可空，也不显示错的
        r = FakeRouter({
            "deviceinfo": dict(DEVICEINFO),
            "ipv6_wan": {"DnsServer": "240e:5a::6666",
                         "Prefix": "240e:3a5:4801:1600::/64"},
        })
        self.assertEqual(router_info.collect(r)["wan6"], "")

    def test_wan4_unchanged(self):
        r = FakeRouter({
            "deviceinfo": dict(DEVICEINFO),
            "wan": {"WanIPv4": "58.208.16.212", "DnsServer": "218.2.2.2"},
        })
        self.assertEqual(router_info.collect(r)["wan4"], "58.208.16.212")


class VersionTest(unittest.TestCase):
    def test_harmony_and_firmware(self):
        r = FakeRouter({"deviceinfo": dict(DEVICEINFO)})
        out = router_info.collect(r)
        self.assertEqual(out["firmware"], "6.1.0.20(V7R2)")
        self.assertEqual(out["harmony"], "6.1.0")

    def test_software_dash_means_missing(self):
        info = dict(DEVICEINFO, SoftwareVersion="-")
        out = router_info.collect(FakeRouter({"deviceinfo": info}))
        self.assertEqual(out["firmware"], "")
        self.assertEqual(out["harmony"], "6.1.0")

    def test_hardware_mac_uptime(self):
        out = router_info.collect(FakeRouter({"deviceinfo": dict(DEVICEINFO)}))
        self.assertEqual(out["hardware"], "VER.A")
        self.assertEqual(out["wan_mac"], "40:06:34:65:84:22")
        self.assertEqual(out["lan_mac"], "40:06:34:65:84:22")
        self.assertEqual(out["uptime"], "3 天 4 小时")


class WifiTest(unittest.TestCase):
    def test_separate_bands_with_channels(self):
        r = FakeRouter({
            "deviceinfo": dict(DEVICEINFO),
            "wlan": {"WifiSsid24G": "Home", "WifiSsid5G": "Home-5G"},
            "channelinfo": {"Channel2G": 6, "Channel5G": 149,
                            "ChannelDeploy": 1, "NetChannelMode": 3},
        })
        out = router_info.collect(r)
        self.assertEqual(out["ssid"], {"2.4G": "Home", "5G": "Home-5G"})
        self.assertEqual(out["channels"], {"2.4G": 6, "5G": 149})

    def test_band_steering_merges(self):
        """双频合一：两个频段同名 → 合并成一个键。"""
        r = FakeRouter({
            "deviceinfo": dict(DEVICEINFO),
            "wlan": {"WifiSsid24G": "Home", "WifiSsid5G": "Home"},
            "channelinfo": {"Channel2G": 6, "Channel5G": 149},
        })
        out = router_info.collect(r)
        self.assertEqual(out["ssid"], {"双频合一": "Home"})
        self.assertEqual(out["channels"], {"2.4G": 6, "5G": 149})

    def test_mode_and_deploy_never_read_as_channel(self):
        r = FakeRouter({
            "deviceinfo": dict(DEVICEINFO),
            "channelinfo": {"ChannelDeploy": 1, "NetChannelMode": 3},
            "wlanradio": {"PowerMode": 2},
        })
        out = router_info.collect(r)
        self.assertEqual(out["channels"], {})
        self.assertEqual(out["power_mode"], 2)

    def test_channel_value_must_be_in_range(self):
        r = FakeRouter({
            "deviceinfo": dict(DEVICEINFO),
            "channelinfo": {"Channel2G": 99, "Channel5G": 200},
        })
        self.assertEqual(router_info.collect(r)["channels"], {})

    def test_no_wifi_interfaces_returns_empty(self):
        out = router_info.collect(FakeRouter({"deviceinfo": dict(DEVICEINFO)}))
        self.assertEqual(out["ssid"], {})
        self.assertEqual(out["channels"], {})


class LanTest(unittest.TestCase):
    def test_prefix_and_lan_ip(self):
        r = FakeRouter({
            "deviceinfo": dict(DEVICEINFO),
            "ipv6_lan": {"Prefix": "240e:3a5:4801:1600::/64",
                         "LanIPAddress": "192.168.3.1"},
        })
        out = router_info.collect(r)
        self.assertEqual(out["prefix6"], "240e:3a5:4801:1600::/64")
        self.assertEqual(out["lan_ip4"], "192.168.3.1")


class EmptyTest(unittest.TestCase):
    def test_everything_404_stays_empty(self):
        out = router_info.collect(FakeRouter({}))
        for k in ("product", "model", "hardware", "firmware", "harmony",
                  "uptime", "wan4", "wan6", "lan_ip4", "prefix6",
                  "wan_mac", "lan_mac"):
            self.assertEqual(out[k], "", k)
        self.assertEqual(out["ssid"], {})
        self.assertEqual(out["channels"], {})
        self.assertIsNone(out["power_mode"])

    def test_never_raises(self):
        class Boom:
            def get(self, name, params=None):
                raise RuntimeError("boom")
        router_info.collect(Boom())          # 不应抛异常


class RealQ7Test(unittest.TestCase):
    """按真机抓包（凌霄子母路由 Q7 网线版）的返回体形状回归。

    真机教训（1.2.2 修）：
      · v4 / v6 地址都在 `ntwk/wan` 里，而 `IPv4Gateway` / `IPv6DnsServers`
        排在真地址前面 —— 泛扫会把网关和 DNS 当成 WAN 地址显示出来；
      · 下发前缀是 `IPv6PrefixList`，原来按「键名带 prefix」取不到（空）；
      · SSID 不在 `ntwk/wan`/`ntwk/wlan` 里，在 `ntwk/WlanGuideBasic`
        的 `WifiConfig[]` 中（每项自带 FrequencyBand + Channel）。
    """

    WAN = {
        "IPv4Gateway": "58.208.16.193",
        "IPv4DnsServers": "218.2.2.2,218.4.4.4",
        "IPv4Addr": "58.208.16.212",
        "IPv6AddrSet": "240e:3a0:483c:e239:2c4f:9fdb:e3ea:edc7",
        "IPv6Addr": "240e:3a0:483c:e239:2c4f:9fdb:e3ea:edc7/64",
        "IPv6AddrPrefixLen": 64,
        "IPv6DnsServers": "240e:5a::6666,240e:5b::6666",
        "IPv6Gateway": "fe80::200:5eff:fe00:108",
        "IPv6PrefixList": "240e:3a5:4801:1600::/64",
    }

    WLANBASIC = {"WifiConfig": [
        {"WifiSsid": "HOME", "FrequencyBand": "2.4GHz", "Channel": 1,
         "ID": "InternetGatewayDevice.X_Config.Wifi.Radio.1.Ssid.1."},
        {"WifiSsid": "HOME", "FrequencyBand": "5GHz", "Channel": 44,
         "ID": "InternetGatewayDevice.X_Config.Wifi.Radio.2.Ssid.1."},
    ]}

    def test_wan4_is_address_not_gateway(self):
        out = router_info.collect(FakeRouter({"deviceinfo": dict(DEVICEINFO),
                                             "wan": dict(self.WAN)}))
        self.assertEqual(out["wan4"], "58.208.16.212")

    def test_wan6_is_address_not_dns(self):
        out = router_info.collect(FakeRouter({"deviceinfo": dict(DEVICEINFO),
                                             "wan": dict(self.WAN)}))
        self.assertEqual(out["wan6"], "240e:3a0:483c:e239:2c4f:9fdb:e3ea:edc7")
        self.assertNotIn("6666", out["wan6"])

    def test_prefix_comes_from_prefixlist(self):
        out = router_info.collect(FakeRouter({"deviceinfo": dict(DEVICEINFO),
                                             "wan": dict(self.WAN)}))
        self.assertEqual(out["prefix6"], "240e:3a5:4801:1600::/64")

    def test_prefix_never_falls_back_to_wan_address(self):
        body = dict(self.WAN)
        body.pop("IPv6PrefixList")
        out = router_info.collect(FakeRouter({"deviceinfo": dict(DEVICEINFO),
                                             "wan": body}))
        self.assertEqual(out["prefix6"], "")
        self.assertEqual(out["wan6"], "240e:3a0:483c:e239:2c4f:9fdb:e3ea:edc7")

    def test_wificonfig_gives_ssid_and_channels(self):
        out = router_info.collect(FakeRouter({
            "deviceinfo": dict(DEVICEINFO),
            "wlanbasic": dict(self.WLANBASIC),
        }))
        self.assertEqual(out["ssid"], {"双频合一": "HOME"})
        self.assertEqual(out["channels"], {"2.4G": 1, "5G": 44})

    def test_wificonfig_split_names(self):
        cfg = [dict(self.WLANBASIC["WifiConfig"][0]),
               dict(self.WLANBASIC["WifiConfig"][1], WifiSsid="HOME-5G")]
        out = router_info.collect(FakeRouter({
            "deviceinfo": dict(DEVICEINFO),
            "wlanbasic": {"WifiConfig": cfg},
        }))
        self.assertEqual(out["ssid"], {"2.4G": "HOME", "5G": "HOME-5G"})

    def test_band_falls_back_to_radio_id(self):
        cfg = [{"WifiSsid": "A", "Channel": 6,
                "ID": "...Wifi.Radio.1.Ssid.1."},
               {"WifiSsid": "B", "Channel": 149,
                "ID": "...Wifi.Radio.2.Ssid.1."}]
        out = router_info.collect(FakeRouter({
            "deviceinfo": dict(DEVICEINFO),
            "wlanbasic": {"WifiConfig": cfg},
        }))
        self.assertEqual(out["channels"], {"2.4G": 6, "5G": 149})
        self.assertEqual(out["ssid"], {"2.4G": "A", "5G": "B"})


if __name__ == "__main__":
    unittest.main()
