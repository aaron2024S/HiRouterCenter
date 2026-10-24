# -*- coding: utf-8 -*-
"""设备类型：内置图标集 + 自动识别 + 用户手改。

三级来源，优先级从高到低：

  1. 用户在网页上点选的（存 /data/devtypes.json，MAC → 类型）
  2. 固件 HostInfo 里带的类型字段（若能读到，见 DEV_FIELDS）
  3. 按设备名关键词猜（本文件 TYPES_RULES）

为什么要有这一层：设备列表里一排「首字母方块」看不出谁是谁，而路由器给的
只有 MAC 和名字。类型只影响图标与筛选，猜错也不会有副作用 —— 用户点一下就能改，
所以这里可以放心用关键词去猜。

存储刻意做成「只存用户改过的」：文件不存在 / 没有这条 MAC，就走自动识别。
这样新增设备不需要维护任何东西，删了文件也只是回到自动识别。
"""
from __future__ import annotations

import json
import logging
import os
import re

from . import discover

log = logging.getLogger("ipv6sync.devtypes")

# (id, 显示名)。id 同时是前端图标 symbol 的后缀（#t-<id>），改动要同步前端。
TYPES = [
    ("nas", "NAS / 存储"),
    ("pc", "台式机"),
    ("laptop", "笔记本"),
    ("phone", "手机"),
    ("tablet", "平板"),
    ("watch", "手表 / 手环"),
    ("tv", "电视"),
    ("projector", "投影仪"),
    ("tvbox", "机顶盒"),
    ("speaker", "音箱"),
    ("camera", "摄像头"),
    ("printer", "打印机"),
    ("router", "路由器 / AP"),
    ("console", "游戏机"),
    ("fridge", "冰箱"),
    ("washer", "洗衣机"),
    ("ac", "空调"),
    ("vacuum", "扫地机"),
    ("light", "灯"),
    ("plug", "插座 / 开关"),
    ("lock", "门锁"),
    ("cooker", "厨房电器"),
    ("car", "车机"),
    ("iot", "传感器 / 网关"),
    ("bath", "浴霸"),
    ("waterheater", "热水器"),
    ("purifier", "净水 / 饮水机"),
    ("fan", "风扇"),
    ("airpur", "空气净化器"),
    ("curtain", "窗帘 / 晾衣机"),
    ("scale", "体重秤"),
    ("vr", "VR 眼镜"),
    ("ricecooker", "电饭煲"),
    ("heater", "取暖器 / 电热毯"),
    ("unknown", "未知设备"),
]

TYPE_NAME = dict(TYPES)
TYPE_IDS = tuple(t for t, _ in TYPES)

# 顺序即优先级：越具体的规则越靠前。
# 「switch」放游戏机而不是网络交换机 —— 家庭场景里 Switch 几乎都是游戏机；
# 「灯 / 插座」必须早于「路由」的 wifi 规则，否则「wifi 插座」会被认成路由器。
_RULES = [
    (r"nas|群晖|威联通|铁威马|空间|绿联|存储|synology|qnap|unraid|ds9\d\d", "nas"),
    (r"笔记本|laptop|macbook|thinkpad|notebook|小新|拯救者", "laptop"),
    (r"台式|desktop|主机|workstation|\bpc\b|树莓派|raspberry|服务器|server", "pc"),
    (r"平板|ipad|tablet|matepad|\bpad\b", "tablet"),
    (r"手机|iphone|phone|畅享|荣耀|redmi|红米|pixel|galaxy", "phone"),
    (r"手表|手环|watch|band", "watch"),
    (r"投影|projector|极米|xgimi|当贝", "projector"),
    (r"电视|bravia|智慧屏|\btv\b", "tv"),
    (r"盒子|机顶盒|appletv|电视果|\bbox\b", "tvbox"),
    (r"音箱|speaker|sound|小爱|天猫精灵|homepod|sonos|小度|echo", "speaker"),
    (r"摄像|camera|cam\b|门铃|doorbell|萤石|监控", "camera"),
    (r"打印|printer|canon|epson|brother|\bhp\b", "printer"),
    (r"插座|插排|排插|plug|智能开关", "plug"),
    (r"灯泡|吸顶灯|筒灯|台灯|\blight\b|bulb|lamp|yeelight", "light"),
    (r"扫地|扫拖|vacuum|roborock|石头|科沃斯|追觅", "vacuum"),
    (r"冰箱|fridge|refrigerator", "fridge"),
    (r"洗衣机|washer|washing", "washer"),
    (r"空调|aircon|格力|美的|\bac\b", "ac"),
    (r"浴霸|yuba|暖浴", "bath"),
    (r"热水器|water.?heater", "waterheater"),
    (r"净水|饮水|water.?purif|drinking", "purifier"),
    (r"风扇|塔扇|落地扇|\bfan\b", "fan"),
    (r"净化|新风|air.?purif", "airpur"),
    (r"窗帘|晾衣|curtain", "curtain"),
    (r"体重秤|体脂秤|\bscale\b", "scale"),
    (r"\bvr\b|眼镜|\bvr ?头", "vr"),
    (r"电饭煲|电饭锅|煮饭|rice.?cooker", "ricecooker"),
    (r"取暖|电热毯|暖风机|电暖|heater", "heater"),
    (r"门锁|智能锁|\block\b|猫眼", "lock"),
    (r"饭煲|电饭|微波|烤箱|咖啡机|净水|cooker|oven|kettle", "cooker"),
    (r"游戏|switch|xbox|playstation|ps[45]\b|steam\s?deck|手柄|console", "console"),
    (r"车机|行车|tesla|\bcar\b", "car"),
    (r"路由|router|mesh|无线|子母|\bap\b", "router"),
    (r"传感|sensor|网关|gateway|温湿|人体|门窗|zigbee|hub", "iot"),
]
_COMPILED = [(re.compile(p, re.I), t) for p, t in _RULES]

# 固件 HostInfo 里可能出现的类型字段（不同固件/版本不一）。
# 读得到就比关键词准 —— 但真机上得先确认有这个字段，读不到不报错。
DEV_FIELDS = ("DevType", "DeviceType", "devType", "IconType", "iconType", "Type")
# 固件若给的是数字或枚举字符串，用这张表翻译；不认识的忽略，别乱映射。
_DEV_VALUE_MAP = {
    "1": "phone", "2": "pc", "3": "tablet", "4": "tv", "5": "camera",
    "6": "printer", "7": "router", "8": "speaker", "9": "nas",
    "phone": "phone", "mobile": "phone", "pc": "pc", "computer": "pc",
    "tablet": "tablet", "pad": "tablet", "tv": "tv", "stb": "tvbox",
    "box": "tvbox", "camera": "camera", "ipc": "camera", "printer": "printer",
    "router": "router", "ap": "router", "speaker": "speaker",
    "nas": "nas", "storage": "nas", "watch": "watch", "iot": "iot",
}


def path_for(state_file: str) -> str:
    """类型文件与 state.json 同目录（默认 /data/devtypes.json）。"""
    d = os.path.dirname(os.path.abspath(state_file or "/data/state.json"))
    return os.path.join(d, "devtypes.json")


def load(state_file: str) -> dict:
    """读用户手工指定的类型：{规范 MAC: 类型 id}。坏文件当空表处理。"""
    path = path_for(state_file)
    try:
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
    except (OSError, ValueError):
        return {}
    if not isinstance(raw, dict):
        return {}
    out = {}
    for k, v in raw.items():
        mac = discover.norm_mac(str(k))
        if mac and v in TYPE_NAME:
            out[mac] = v
    return out


def save(state_file: str, mapping: dict) -> None:
    """原子写（先写临时文件再 rename，掉电不会留半个文件）。"""
    path = path_for(state_file)
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(mapping, f, ensure_ascii=False, indent=1, sort_keys=True)
    try:
        os.chmod(tmp, 0o600)
    except OSError:
        pass
    os.replace(tmp, path)


def set_type(state_file: str, mac: str, type_id: str) -> dict:
    """指定一台设备的类型。传 unknown 等价于「恢复自动识别」（把记录删掉）。"""
    mac = discover.norm_mac(mac)
    if not mac:
        raise ValueError("MAC 地址不合法")
    if type_id not in TYPE_NAME:
        raise ValueError("未知的设备类型")
    mapping = load(state_file)
    if type_id == "unknown":
        mapping.pop(mac, None)          # 清掉手改，回到自动识别
    else:
        mapping[mac] = type_id
    save(state_file, mapping)
    return {"mac": mac, "type": type_id, "manual": type_id != "unknown"}


def guess(name: str) -> str:
    """按设备名关键词猜类型；一条都匹配不上就是 unknown。"""
    if not name:
        return "unknown"
    for rex, t in _COMPILED:
        if rex.search(name):
            return t
    return "unknown"


def from_host(host: dict) -> str:
    """固件字段 → 类型 id；读不到返回空串。"""
    for k in DEV_FIELDS:
        v = host.get(k)
        if v in (None, ""):
            continue
        t = _DEV_VALUE_MAP.get(str(v).strip().lower())
        if t:
            return t
    return ""


def resolve(host: dict, manual: dict) -> tuple[str, bool]:
    """返回 (类型 id, 是否用户手工指定)，三级回退。"""
    mac = discover.norm_mac(str(host.get("MACAddress") or ""))
    if mac and mac in manual:
        return manual[mac], True
    t = from_host(host)
    if t:
        return t, False
    return guess(str(host.get("ActualName") or host.get("HostName") or "")), False
