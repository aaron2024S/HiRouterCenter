# 华为 Q7 网线版（MEDUSA2-BR80）固件接口档案

> 本文件是**本地真机取证结果**，用于后续开发新功能时免去重新抓包。
> 所有示例值已脱敏（MAC / IP / 序列号 / 宽带账号 / Wi-Fi 名称一律替换为占位符）。
> 真机原始样本留在 `.tmp-render/fw-live/`（被 `.gitignore` 排除，不进仓库）。

## 0. 采集环境

| 项 | 值 |
|---|---|
| 机型 | 华为凌霄子母路由 Q7 网线版（MEDUSA2-BR80-10） |
| 友好名 | 华为凌霄子母路由 Q7 网线版 |
| 软件版本 | `6.1.0.20(V7R2)` |
| HarmonyOS | `6.1.0` |
| EMUI | `3.0.1.3(C01)` |
| RouterType | `router_huawei_switch` |
| 硬件版本 | `VER.A` |
| 管理地址 | `http://192.168.3.1` |
| 前端入口 | `/html/index.html`（Vue 3 + vue-router，history 模式） |
| 采集日期 | 2026-10-30 |

### 采集方式

1. **免登录静态取证**：`/html/index.html` → `/js/main.js` → 按 chunk 命名规则批量下载 43 块 JS（1.6MB）到 `.tmp-render/fw/`。
   - chunk 路径：`/html/js/{name}.cec36951eeffdb941a88.js`，`{0:"common", 1:"wlanauthorizeredirect", 其余用数字 id}`
2. **登录后动态取证**：Playwright 拉起系统 Edge，用户手动登录（脚本不接触密码），
   再在页面上下文里用 `fetch`（`credentials:"include"` + 固件的 CSRF 头）逐个 GET 读接口。
3. **文案包**：`/lang/zh/{name}_res.js`（`name` 见 §5 功能地图），共 72 份 159KB。

**重抓用的脚本在 [`tools/firmware-probe/`](../tools/firmware-probe/)**（已随仓库提供，见该目录 README）：
`fw-crawl.js`（全量抓取）、`fw-reprobe.js`（404 接口复探）、`fw-headers.js`（请求头矩阵）、
`fw-live-grab2.js`（被动监听固件自身请求）。全部只发 GET、不接触密码。

---

## 1. 设备身份与能力

### 1.1 身份字段（`GET /api/system/deviceinfo`）

| 字段 | 值 | 说明 |
|---|---|---|
| `FriendlyName` | 华为凌霄子母路由 Q7 网线版 | 展示名 |
| `DeviceName` | Huawei | — |
| `SoftwareVersion` | 6.1.0.20(V7R2) | 固件版本 |
| `HardwareVersion` | VER.A | — |
| `RouterType` | router_huawei_switch | — |
| `UpTime` | 秒 | 本次启动时长 |
| `MacFilterCapacity` | **256** | **MAC 过滤表容量**（早前从 JS 推断的 32 是旧默认值，真机是 256） |
| `ManufacturerOUI` | 00E0FC | — |
| `NetType` / `NetAccessCode` | — | 运营商网络类型/代码（敏感，略） |
| `custinfo.CustDeviceName` | MEDUSA2-BR80-10 | 内部机型代号 |
| `custinfo.CustDeviceBand` | 1 | — |
| `other.guide` | true | 引导流程状态 |
| `other.FirstLogin` | 1 | 是否首次登录 |
| `other.IsNeedSalt` | true | 登录加盐 |

### 1.2 `modcap` 能力表（69 项，决定界面显示哪些功能）

**支持（值 ≠ 0）的 41 项：**

| 能力 | 值 | 含义 |
|---|---|---|
| `wifiCap` | 21 | Wi-Fi 能力位 |
| `isSupport80211AX` / `isSupport80211BE` | 1 / 1 | 支持 Wi-Fi 6 / Wi-Fi 7 |
| `isSupportWpa3` | 1 | WPA3 |
| `isSupportWifiDbho` | 1 | 双频优选 |
| `isSupportWlanFilterEnhance` | 1 | **增强版 MAC 过滤（本程序黑名单用的就是它）** |
| `isSupportWlanTimeSwitchEnhance` | 1 | Wi-Fi 定时开关增强 |
| `isSupportQueryAndSetChannel` | 1 | 可查/可设信道 |
| `isSupport5gChannelOptimize` | 1 | 5G 信道优化 |
| `isSupportDiagnose2G` / `isSupportDiagnose5G` | 1 / 2 | 2.4G / 5G 诊断 |
| `isSupportQosNewConfig` / `isSupportQosBwConfig` | 2 / 2 | 新版 QoS 配置 |
| `isSupportQos...` + `isSupportServiceClassifyIdList` | 1 | 应用识别 QoS |
| `isSupportGameV2` / `isSupportAiGame` | 1 / 1 | 游戏加速 |
| `isSupportBackhaul` | 1 | 回程（Mesh 有线/无线回程） |
| `isSupportNtwkCapCompare` | 1 | 网络能力比对 |
| `isSupportIPv6AutoPassthrough` | 1 | IPv6 自动穿透 |
| `isSupportIptv`（`support_iptv`） | 1 | IPTV |
| `isSupportDc` | 1 | 疑似「双连接/双频合一」 |
| `isSupportFanControl` | 3 | 风扇控制（3 档？） |
| `isSupportFreeControl` | 1 | — |
| `isSupportHilinkCap` / `isSupportHilinkMess` | 1 / 1 | 智联能力/消息 |
| `isSupportNewDeviceAdd` | 1 | 新设备接入提醒 |
| `isSupportMarketPluginMatch` / `isSupportPluginAutoUpg` / `isSupportPluginPageOptimize` / `isSupportPluginDataBI` | 1 | 插件市场 |
| `isSupportStatement` | 1 | 隐私声明 |
| `isSupportHissidOpt` | 1 | 隐藏 SSID 优化 |
| `isSupportZhSSID` | 1 | 支持中文 SSID |
| `isSupportGuestExtendRestTime` | 1 | 访客网络可延长 |
| `isSupportNextTimeUp` | 1 | — |
| `isSupportMaxHisRate` | 1 | 历史最高速率 |
| `isSupportGuideOptimize` | 1 | 引导流程优化 |
| `iswifi5Compat` | 1 | Wi-Fi 5 兼容网络 |
| `supportWSControl` | 1 | — |
| `SupportRegType` | 999 | 注册类型 |
| `backup_ver` | 1 | 配置备份版本 |

**不支持（值 = 0）的 28 项 —— 这些功能在本机型上不要做：**

```
isSupportNFC              isSupportPowerKey        isSupportHybrid
isSupportEthBrdgConfig    isSupportDelMpsDevice    isNotSupportGuest5G
support_urlflt            support_macflt           support_ipv6_enable
support_andlink           support_andlink_v2       support_elink
support_wolink            support_xlink_sn         support_telecom_pd
support_cloud_mac_filter  support_ruleStatus       support3rdDevlist
supportIfttt              support_router_custom    support_html_custom_app
support_guide_ssid        support_guide_start_login support_power_in_wifi_guide
support_test_guide        support_testwifiencrypt  support_wlan_instance_custom
support_zjct_custom
```

⚠️ 注意 `support_urlflt = 0`（**没有网址过滤**）、`support_macflt = 0`（旧 MAC 过滤关闭，改用 `wlanfilterenhance`）、
`isSupportNFC = 0`（没有 NFC 一碰连）。

### 1.3 `devcap`

```
RebootTime: 48           重启耗时（秒）
WIFI: 0
Version: "2.0"
USB: 1                   芯片支持 USB（但本机型无 USB 口，相关接口均 404）
GuestNetwork: 1          支持访客网络
PowerSave: 1
SupportAPP: true
Vendor: "HUAWEI"
HardwareCapability: {0:0, 1:1, 2:1, 3:1, 4:0, 5:0, 6:0, 7:1, 8:0, 9:0, 10:0, 11:0}
SoftwareCapability: {0:2, 2:2, 3:1, 4:1, 5:2, 8:1, 11:1, 13:3, 14:2, 19:1, 20:1, 23:1,
                     24:1, 25:1, 26:1, 27:1, 34:1, 36:1, 38:1, 41:1, 45:1, 55:1, 64:1,
                     65:1, 66:1, 67:1, 69:1, 72:4, 76:1, 77:1, 79:1, 82:1, 83:1, 86:1,
                     90:1, 91:1, 92:1, 96:1, 99:1, 103:1, 104:1, 111:1, 113:1, 114:1,
                     116:1, 117:1, 119:1, 120:1, 121:1, 122:1, 123:3, 124:1, 125:1,
                     126:1, 127:1, 129:1, 130:1, 142:1, 158:1, 159:1, 160:1, 162:1,
                     163:1, 167:1, 168:1, 169:1, 170:3, 172:2, 173:1}
centralCap: "4"
```

`SoftwareCapability` 是编号位掩码，含义未公开。已知一条：**`SoftwareCapability[161]` = 「支持近场自动 Mesh」**
（固件 `isSupportNearAutoMesh()` 直接读它，本机型无 161 键 → 不支持）。

---

## 2. API 总览

固件的 API 基础路径是 **`/api/`**，路由表在 `main.js` 里以 `key:"模块/接口名"` 形式声明，共 **171 条**。
完整表见 `.tmp-render/fw/routes.json`。

请求方式：
- **读**：`GET /api/{模块}/{接口名}`，返回 JSON（数组或对象）
- **写**：`POST /api/{模块}/{接口名}`，body 为 JSON，需带固件的 CSRF 头
- **CSRF**：头名来自 `deviceinfo.csrf_param`，值来自 `deviceinfo.csrf_token`（真机头名需在会话中取）

### 2.1 认证相关（本程序已实现，列出供参考）

| 接口 | 说明 |
|---|---|
| `system/user_login_nonce` | 取登录盐/nonce |
| `system/encpubkey` | 取 RSA 公钥（`EncpubkeyE` / `EncpubkeyN`），密码需 RSA 加密 |
| `system/user_login` | 提交登录 |
| `system/user_login_proof` | 登录校验结果（200 = 成功） |
| `system/user_logout` | 登出 |
| `system/pwd` / `system/pwdrule` | 改密码 / 密码规则 |

### 2.2 本程序当前用到的接口

| 接口 | 用途 |
|---|---|
| `system/HostInfo` | 设备列表（37 台，56 字段，见 §3.1） |
| `system/deviceinfo` | 能力表 / 版本 / MacFilterCapacity |
| `device/topology` | Mesh 拓扑树（见 §3.3） |
| `ntwk/ip6firewall_enable` | IPv6 防火墙总开关 |
| `ntwk/ip6firewall_trustlist` | IPv6 防火墙白名单条目 |
| `ntwk/wlanfilterenhance` | MAC 黑/白名单（**见 §6 的 404 风险**） |
| `system/changedevicename` | 改设备名（POST） |
| `app/qosclass_host` | 单设备限速（POST） |
| `system/heartbeat` | 会话保活 |

---

## 3. 核心接口字段详解

### 3.1 `GET /api/system/HostInfo` —— 设备列表（最重要）

顶层是**数组**，每项一台设备，**56 个字段**。真机样本 37 台（在线 20 / 离线 17）。

#### 身份

| 字段 | 类型 | 说明 |
|---|---|---|
| `ID` | str | TR-069 节点路径 `InternetGatewayDevice.LANDevice.1.Hosts.Host.N.` |
| `MACAddress` | str | 大写冒号分隔 |
| `IPAddress` | str | IPv4 |
| `IPv6Address` | str | **单个** IPv6（多是 `fe80::` 链路本地） |
| `Ipv6Addrs` | list | `[{Ipv6Addr:"240e:..."}]`，**全局地址在这**（37 台中 14 台有） |
| `domain` | str | `InternetGatewayDevice.LANDevice.1.LANEthernet...`（LAN 口设备才有） |
| `SerialNumber` | str | 子路由才有（4/37） |
| `ProdId` | str | 子路由才有，如 `K1G3` |
| `devId` | str | 子路由 UUID |
| `roomId` / `roomName` | int/str | 房间；**真机全是「未选择房间」，不可用作归属依据** |
| `NearlinkStat` | int | 星闪状态（子路由 15，其余 0） |

#### 名称与类型

| 字段 | 说明 |
|---|---|
| `HostName` | 固件给的名称（子路由形如 `华为凌霄子母路由 Q7 网线版 子路由_0639`） |
| `ActualName` | **用户改过的名称**（27/37 有值；空 = 没改） |
| `DevBrands` | 固件识别的品牌（26/37），如 `Huawei` |
| `ActualManu` | 实际厂商（8/37），如 `UGREEN` / `EZVIZ` |
| `ActualType` | 用户指定的设备类型（9/37），如 `NAS` / `NetworkCamera` |
| `IconType` | 图标类型，如 `router_huawei_panel` |
| `VendorClassID` | DHCP vendor class，**识别设备类型的强信号**：`router` / `udhcp...` / `android-dhcp-8.1.0` / `MSFT 5.0` / `EVE` / `GFY` / `WATCH` / `Bridge` / `openharmony` / `VOG` |

#### 在线状态

| 字段 | 说明 |
|---|---|
| `Active` | bool，是否在线 |
| `Active46` | bool，IPv4/IPv6 活跃（与 Active 一致） |
| `V6Active` | bool，IPv6 活跃 |
| `AccessRecord` | 上线时间，格式 `2026-10-24 12:48:46#1#1`（`#` 前是时间） |
| `OfflineRecord` | 下线时间，格式 `2026-07-02 04:23:58#0#1` |
| `LeaseTime` | DHCP 租约**剩余秒数**（str） |
| `AddressSource` | `DHCP` / `STATIC` |

#### 接入方式与速率（**关键修正**）

| 字段 | 说明 |
|---|---|
| `InterfaceType` | `LAN` / `2.4GHz` / `5GHz` /（固件还认 `DC` / `wifi7-mld` / `PLC`） |
| `Layer2Interface` | **物理口/接入点**：`LAN1`~`LAN4`、`WAN`、`SSID`、`LAN` |
| `Frequency` | `2.4GHz` / `5GHz`，只有无线才有 |
| `rate` | **协商速率，Mbps**。真机实测：LAN 全是 `2500`（2.5G 口）、2.4G 是 6~150、5G 是 6~1921。**离线设备保留最后值** |
| `PhyType` | 全部 `2500`，像是端口物理能力而非协商速率 |
| `rssi` | 信号强度 dBm 绝对值（2.4G 30~70、5G 5~67）；离线保留最后值 |
| `ShowDeviceRealRate` | 全部 `1` |

> ✅ **修正 2026-10-30 之前的错误结论**：曾判断「有线设备拿不到设备级协商速率」。
> 真机证明 `rate` 对有线的值就是端口协商速率（2500 = 2.5G），**Card 上可以显示「有线 · 2.5G」**。

#### 实时与累计流量

| 字段 | 单位 | 说明 |
|---|---|---|
| `DownRate` / `UpRate` | **KB/s** | 实时速率。固件显示时 ×8 转 Kbps。**只有正在跑流量的在线设备才有值**（真机 37 台里仅 4 台有） |
| `RxKBytes` | **KB** | **累计接收（↓）**，30/37 有值，**离线不清零** |
| `TxKBytes` | **KB** | **累计发送（↑）**，同上 |

> 方向判定依据：离线手机 `11.7GB / 1.2GB`、离线台式机 `157GB / 3.2GB` 均符合「Rx=下载、Tx=上传」。
> 固件前端**完全不消费**这两个字段（43 个 chunk 零命中），所以没有官方文案，方向是从样本量级反推的。

#### 限速（QoS）

| 字段 | 说明 |
|---|---|
| `DeviceDownRateEnable` | 限速总开关（bool）。**关着时下面两个值无效** |
| `DeviceMaxUpLoadRate` | 上行上限，**Kbps** |
| `DeviceMaxDownLoadRate` | 下行上限，**Kbps** |
| `ClassQueue` | 全部 `-1`，QoS 队列 |
| `QosclassID` / `PolicerID` | 空 |

写入方式：`POST app/qosclass_host`，**整条 HostInfo 回传**只改这三个字段。

#### 儿童上网 / 家长控制

| 字段 | 说明 |
|---|---|
| `ParentControl` | bool，是否处于管控中（真机全 false） |
| `ParentControlEnable` | **bool，管控开关 —— 这才是判定依据**（真机 4 台为 true） |
| `MacFilterID` | 管控档案路径，如 `InternetGatewayDevice.X_FireWall.ChildDev.7`（4 台有值；空 / `"0"` = 未加入） |

判定逻辑（`app/node.py::_is_kid`）：`ParentControlEnable` 为真 **或** `MacFilterID` 非空 → 受管。

#### Mesh / 子路由标识

| 字段 | 说明 |
|---|---|
| `HiLinkDevice` | **bool，这台设备本身是 HiLink 子路由**（真机仅 4 台为 true）|
| `IsSlave` / `IsSetupSlave` | 同上口径，子路由才 true |
| `HiLinkDevHide` | 在固件某处隐藏（4 台） |

> ❌ **修正**：曾把 `HiLinkDevice` 误解为「是否经子路由接入」。真机证明**所有终端（含挂在子路由下的）都是 false**，
> 只有子路由自己是 true。**不能用它判断终端归属**。

#### 其他

| 字段 | 说明 |
|---|---|
| `Feature` | 位掩码，真机取值只有 `0`(23 台) / `128`(8) / `80`(4) / `1`(2)。**含义未知**，未敢使用 |
| `IsGuest` | 全部 false |
| `WlanActive` / `hwtypeoptionnew` / `supportAbility` | 全 false / 0 / null，无信息量 |
| `IsSupportNoManage` | 全部 `1` |

### 3.2 `GET /api/system/deviceinfo`

见 §1.1 / §1.2 / §1.3。另有 `csrf_param`、`csrf_token`、`uuid`、`EncKey` 等会话字段。

### 3.3 `GET /api/device/topology` —— Mesh 拓扑

**数组，5 项 = 4 个子路由 + 主路由自己**。两种形状：

```jsonc
// 子路由节点
{ "MACAddress":"AA:BB:CC:DD:EE:01", "HiLinkType":"Device", "Active":true, "Name":"",
  "ConnectedDevices":[ {"MACAddress":"...","HiLinkType":"None","Active":true,"ConnectedDevices":[]} ] }

// 主路由自己（形状完全不同！）
{ "MACAddress":"AA:BB:CC:DD:EE:00", "UpdateState":0, "routerSelf":1, "IsSupportOnlineUpg":1 }
```

- `HiLinkType === "Device"` → 路由器/子路由；终端是 `"None"`（不是 `Device`）
- `routerSelf == 1` → 主路由自己（**唯一判据**，该节点没有 ConnectedDevices / Active / HiLinkType）
- **只含在线设备**：真机 17 台离线设备一个都没进拓扑
- 子路由下挂终端在 `ConnectedDevices`，可多层递归

#### 子路由的「连接速率」根本不在拓扑里

拓扑节点**只有 5 个字段**（`MACAddress` / `HiLinkType` / `Active` / `Name` /
`ConnectedDevices`），`Name` 在真机上还全是空串。任何链路信息都得去 `HostInfo`
里找**同一个 MAC** 的那条记录 —— 子路由在 HostInfo 里就是一条普通 Host 记录
（`VendorClassID=router` + `HiLinkDevice=True`）。

| 字段 | 真机值 | 含义 |
|---|---|---|
| `InterfaceType` | `LAN` | 回传方式：LAN / 2.4GHZ / 5GHZ / PLC |
| `Layer2Interface` | `LAN1`…`LAN4` | 插在主路由哪个网口，只有有线才有 |
| `rate` | `2500` | **协商速率，单位 Mbps**（这台 Q7 四个子路由全走 2.5G 口） |
| `PhyType` | `2500` | 端口能力上限 |
| `rssi` | `0` | 无线回传才有意义，有线恒为 0 |
| `Frequency` | `""` | 无线回传频段 |
| `DownRate` / `UpRate` | `0` | **固件不统计子路由自己的实时流量**，恒为 0 |
| `RxKBytes` / `TxKBytes` | `6111` / `107023` | 子路由自己的累计收发（很小，不是下挂终端之和） |
| `ID` | `InternetGatewayDevice.LANDevice.1.Hosts.Host.12.` | 改名要用的编号 |
| `IsSlave` | `true` | 它是从属节点 |
| `IsSetupSlave` | `false` | 是否走「子路由配对流程」加入 |
| `HiLinkDevHide` | `true` | 后端标记「设备列表里藏起来」（43 个 chunk 里**零引用**，纯后端字段） |

**主路由在 HostInfo 里查不到记录**，所以它的链路字段必然为空 —— 前端据此不画链路线。

#### 固件自己怎么显示子路由「速率」（别被它带偏）

`chunk 9` 的 `getTopologyHilinkDevice()`：遍历每个子路由的 `ConnectedDevices`，
把**下挂终端的 `UpRate`/`DownRate` 逐个累加**，赋给这个子路由，存进
`topologyHilinkDevice[MAC]`，再覆盖回设备列表里同名那条记录：

```js
if ("Device" === s.HiLinkType) this.hiLinkTypeDevice(s)   // 嵌套子路由，递归
else { i += c.UpRate; o += c.DownRate }                    // 终端：累加
t.UpRate = i; t.DownRate = o
this.topologyHilinkDevice[e.MACAddress.toUpperCase()] = t
```

⇒ 固件显示的「子路由速率」是**下挂终端实时流量之和**，**不是链路速度**。
真正表示「子路由到主路由这条线有多快」的只有 `rate`。

#### 子路由改名

固件 Web 后台**没给子路由改名入口**（子路由被排除在设备列表外，拓扑页只做展示），
但手机 App 里能改。

接口层：`system/changedevicename` 的 payload 只认 `{ActualName, ID}`
（chunk 9 的 `postName`），**不看设备类型**；子路由在 HostInfo 里就有 `ID`。
固件前端自己还会先把名字 `utf8_strsub(..., 64)` 截到 64 字节。

- **已验证**：payload 形状、ID 来源、名字上限（固件 64 字节，本程序限 20 字）
- **未验证**：后端是否愿意接受对 `VendorClassID=router` 这条 Host 记录的改名请求。
  手机 App 能改 ≠ 本地 HTTP 接口一定放行 —— 真机上点一次才能定论。


### 3.4 `GET /api/hilink/slavedevinfo`

返回 `[]`（本机型空）。另有 `hilink/hilink_status` → `{"hilink_status":1}`、
`hilink/ledstatus` → `{"ErrorCategory":"GetFail","Status":255,...}`。

### 3.5 IPv6 与防火墙

```jsonc
// GET ntwk/ip6firewall_enable
{"Enable": false}

// GET ntwk/ip6firewall_trustlist  —— 数组
[{"Name":"NAS","RemoteIp":"::/0","LocalIp":"240e:...:725d","Port":16669,
  "ID":"InternetGatewayDevice.X_FireWall.Ipv6.Trustlist.1."}]

// GET ntwk/ipv6_enable
{"ID":"InternetGatewayDevice.Services.X_IPv6.","Enable":1}

// GET ntwk/ipv6_wan —— WAN 侧 IPv6
{"X_IPv6DNSServerOne":"240e:xxxx::1","X_IPv6DNSServerTwo":"240e:xxxx::2",
 "X_IPv6PrefixLength":64,"X_IPv6AddressingType":"SLAAC",
 "X_IPv6Address":"240e:xxxx:...:xxxx","X_IPv6DefaultGateway":"fe80::...",
 "X_IPv6DNSOverrideAllowed":false,"X_IPv6IsAutoConfig":false,"X_IPv6DNSEnabled":true,
 "ID":"InternetGatewayDevice.WANDevice.1.WANConnectionDevice.1.WANPPPConnection.1."}

// GET ntwk/ipv6_lan —— LAN 侧（SLAAC + DHCPv6）
{"SLAAC":{"SLAAC_Prefix":"","SLAAC_PrefixLength":64,"SLAAC_Preferredlifetime":3600,
          "SLAAC_Validlifetime":7200,"SLAAC_RouterAdvertisementEnable":true,
          "SLAAC_UseAllocatedWAN":"UseAllocatedSubnet"},
 "DHCP6s":{"DHCP6s_Prefix":"","DHCP6s_PrefixLength":64,"DHCP6s_DHCPServerEnable":true, ...},
 "WanLinkAddr":"fe80::...","LanLinkAddr":"fe80::..."}
```

### 3.6 LAN / DHCP

```jsonc
// GET ntwk/lan_ipaddressreserve —— 静态地址绑定（数组）
[{"ID":"...DHCPStaticAddress.1.","Chaddr":"AA:BB:CC:DD:EE:FF",
  "Yiaddr":"192.168.3.100","Enable":true}]

// GET ntwk/lan_server —— DHCP 服务
{"MinIP":"192.168.3.2","MaxIP":"192.168.3.254","ServerEnable":true,
 "DNSLeaseTime"… "DHCPLeaseTime":86400,"dnsmode":"true",
 "DNSServerone":"...","DNSServertwo":"...","PassThroughLease":60}

// GET ntwk/lan_all —— 所有 LAN 口 IP（数组，2 项）
[{"ID":"...LANDevice.1...","IPInterfaceIPAddress":"192.168.3.1","IPInterfaceSubnetMask":"255.255.255.0"},
 {"ID":"...LANDevice.2...", ...}]

// GET ntwk/lan_host —— 主 LAN 接口
{"FirstEnable":true,"FristIP":"192.168.3.1","FirstMac":"255.255.255.0", ...}

// GET ntwk/lan_upnp → {"enable":true}
// GET ntwk/lan_upnp_portmapping → []（空）
```

### 3.7 有线口协商速率（**「有线 2.5G」的真实来源**）

```jsonc
// GET ntwk/ethnegotiation
{"ethintflist":[
  {"Status":1,"PortName":"LAN1","diaplayName":"LAN1","Speed":2500},
  {"Status":1,"PortName":"LAN2","diaplayName":"LAN2","Speed":2500},
  {"Status":1,"PortName":"LAN3","diaplayName":"LAN3","Speed":2500},
  {"Status":1,"PortName":"LAN4","diaplayName":"LAN4","Speed":2500},
  {"Status":0,"PortName":"LAN5","diaplayName":"LAN5","Speed":0},
  {"Status":0,"PortName":"LAN6","diaplayName":"LAN6","Speed":0},
  {"Status":1,"PortName":"WAN","diaplayName":"WAN","Speed":1000},
  {"Status":0,"PortName":"LAN7","diaplayName":"LAN7","Speed":0}]}
```

- `Status` 1 = 已连接，0 = 未连接
- `Speed` 单位 Mbps
- ⚠️ 字段名 `diaplayName` 是固件自己的拼写错误（不是 displayName）

### 3.8 WAN / 上网

```jsonc
// GET ntwk/wandetect —— 上网状态总览
{"AccessStatus":"Up","ConnectionStatus":"Connected","Status":"Connected",
 "AccessType":"Ethernet","ConnectionType":"PPP_Routed","ErrReason":"Success",
 "DetailErr":"","SearchingStatus":"Finished","HttpStatus":2,
 "DefaultGateway":"192.168.3.1","DNSServers":"...","ExternalIPAddress":"...",
 "IPv4Enable":true,"IPv6Enable":true,"IPv6ConnectionStatus":"Connected",
 "IPv6Address":"240e:xxxx:.../64","IPv6DefaultGateway":"fe80::...",
 "IPv6PrefixList":"240e:xxxx:xxxx:xxxx::/64","IPv6PrefixLength":64,
 "IPv6AddressingType":"SLAAC","AutoFlag":"0","BackupStatus":1,"Uptime":540451}

// GET ntwk/wan?type=active（也可用 doublewan / manywan，都是 ntwk/wan）
// 数组，每项一个 WAN 连接，字段极多：PPPDialIpMode/Name/Alias/Enable/AccessType/
// MACColoneEnable/WanType/ConnectionStatus/Username/ServiceList/MRU/MTU/
// PPPAuthMode/MSS/PPPTrigger/NATType/IPv4AddrType/IPv4Enable/IPv4Addr/
// IPv4Mask/IPv4Gateway/IPv4DnsServers/IPv6Enable/IPv6AddrType/... UpBandwidth
// ⚠️ 含宽带账号明文（Username），日志/界面绝不能输出
```

### 3.9 Wi-Fi

```jsonc
// GET ntwk/wlanradio —— 射频总开关
{"Enable5G":true,"Enable2G":true,"InitEnable2G":false,"PowerMode":1,
 "InitEnable5G":false,"PowerModeChgTip":false,"WLANMode":0}

// GET ntwk/channelinfo —— 各节点信道与评分（Wi-Fi 优化的数据源）
{"HideChannelMode":0,"NetStatus":0,
 "WifiStatus":[{"Name":"子路由_书房","ProId":"K1G3","MacAddress":"...",
   "ChannelInfo":[
     {"Status":0,"Channel":11,"FrequencyBand":"2.4GHz",
      "ChannelList":"1,2,3,...,13,","Value":"7,7,7,7,7,7,7,7,8,8,8,8,8,"},
     {"Status":0,"Channel":44,"FrequencyBand":"5GHz",
      "ChannelList":"36,40,44,48,52,56,60,64,149,153,157,161,",
      "Value":"10,10,10,10,4,4,4,4,8,6,6,5,"}]}]}

// GET ntwk/wlanmode
{"ConnectState":"Disconnected","EmRouterRole":0,"HilinkStatus":0,"WLANMode":0}

// GET ntwk/wlandbho —— 双频优选 / MLO
{"MloEnable":true,"DbhoEnable":true}

// GET ntwk/wlanintelligent —— 智联
{"ID":"...Radio.1.Ssid.1.HiLinkDevice.","enable":true,"ntwksyncEnable":false}

// GET ntwk/wlanwifisync —— Wi-Fi 同步
{"WifisyncStatus":true,"wifiPowerStatus":true}

// GET ntwk/wlantimeaccelerate —— 定时加速
{"AccelerateTime":"18:00","Records":[],"Enable":false}
```

> ⚠️ 路径大小写不一致：`wlanTimingAccelerate` → 实际路由名 `ntwk/wlantimeaccelerate`（全小写）。

### 3.10 安全功能

```jsonc
// GET ntwk/firewall —— 防火墙等级
{"ArpAttack":false,"CurrentLevel":"Low","SetLevel":"Low","SynFlooding":true,"IcmpFlooding":false}

// GET ntwk/dmz
{"Enable":false,"HostIPAddress":"","IPAddress":"","HostName":""}

// GET ntwk/homesec_stealnet —— 防蹭网/防泄漏
{"AntiLeakageCapability":true,"StealNetModel":0,"Info":{"Cipher":{"AbfaEnable":true}}}

// GET ntwk/portmapping → []   端口映射（空）
// GET ntwk/porttrigger → []   端口触发（空）
// GET ntwk/urlfilter   → []   网址过滤（空；且 modcap.support_urlflt=0，本机型不支持）
```

### 3.11 其他

```jsonc
// GET system/device_count —— 设备计数（侧栏角标可用）
{"LanActiveNumber":7,"HiLinkDevNum":4,"UserNumber":1,"ActiveDeviceNumbers":20}
// LanActiveNumber = 有线在线；HiLinkDevNum = 子路由数；ActiveDeviceNumbers = 总在线

// GET ntwk/sntp —— 时间
{"NTPServer1":"cn.pool.ntp.org","NTPServer2":"asia.pool.ntp.org",
 "Status":"Synchronized","SntpIsSynchronizedStatus":true,
 "LocalTimeZoneName":"GMT-08:00","TimeZoneIdx":80,"CurrentLocalTime":"2026-10-30T19:12:31"}

// GET app/speedtest —— 测速结果（Kbps）
{"SpeedtestResult":1,"SpeedtestStatus":0,"DownBandwidth":953005,"UpBandwidth":62032}

// GET ntwk/guest_network_limitrate —— 访客网络限速
{"PeakRate":0,"X_DownPeakRate":1250000,"phyType":2500,"Enable":0}

// GET ntwk/repeaterstate —— 中继状态
{"bssid":"","connstate":"Disconnected","signal":"","channel":"","speed":"",
 "ssid":"","Wlan24SSID":"HOME","Wlan5SSID":"HOME","radio":"","wifiConnectState":0,
 "WifiSsidFactory":"HUAWEI-..."}   // WifiSsidFactory = 出厂 SSID

// GET ntwk/backhaul → {"pwd":"********"}   回程密码（已打码，写入需谨慎）

// GET ntwk/iptv —— IPTV 配置
{"AutoBindEnable":true,"SlaveList":[{"Active":1,"Bind":false,"MACAddress":"...",
  "Layer2Interface":"LAN2","HostName":"子路由A"}],
 "PortNum":7,"FixWanPort":0,"VLANEnable":false,"VLANMode":"Custom","Enable":false,
 "AccessType":"Ethernet2","VLANId":1,"VLAN1p":0,"PVC":"PVC:8/35","SnoopingEnable":true}

// GET ntwk/ddns → 全空（未启用）
// GET ntwk/timedredial → {"RedialTime":"05:00","Enable":false}
// GET ntwk/wansearchcontrol → {"Enable":false,"WanInterface":"..."}
// GET system/forceupgcfg → {"StartTime":"03:00","EndTime":"05:00","Enable":true}
// GET system/location → {"isRemote":false}
// GET app/privacypolicy → 隐私声明地址与版本
// GET ntwk/getmacaddress → {"macaddress":"...","ipaddress":"192.168.3.1"}（主路由 MAC）
// GET app/application / app/applicationitems → []（未装插件）
// GET device/topology → 见 §3.3
```

---

## 4. 写接口（POST）与风险

以下接口的**写**操作已知或已取证，执行前必须清楚后果：

| 接口 | 动作 | 风险 |
|---|---|---|
| `system/changedevicename` | `{action:"update", data:[{ActualName, ID}]}` | 低。名称限制 64 字节 |
| `app/qosclass_host` | **整条 HostInfo 回传**，只改 `DeviceMax*Rate` / `DeviceDownRateEnable` | 中。字段漏传可能清空配置 |
| `ntwk/wlanfilterenhance` | 整份 2.4G/5G 配置回传 | **高**。字段名见 §6 风险，写错会踢掉所有已连设备 |
| `ntwk/ip6firewall_enable` | 整对象回传 | 中。关掉后 IPv6 全暴露 |
| `ntwk/ip6firewall_trustlist` | 整数组回传 | 中。漏条目会删规则 |
| `system/reboot` / `system/delayreboot` | 重启 | **高** |
| `system/restorestate` | 恢复出厂 | **极高，禁止** |
| `device/uploadimage` / `system/*upg*` | 升级固件 | **极高，禁止** |
| `system/pwd` / `system/useraccount` | 改密码/账号 | 高 |
| `ntwk/wlanradio` | 关射频 | 高（会影响所有无线设备） |

---

## 5. 功能地图（固件页面 ↔ 语言包 ↔ 接口）

前端是 Vue 3 SPA，一级导航 5 个，其余在「更多功能」下。

```
Nav:  home(主页) / internet(我要上网) / wifi(我的 Wi-Fi) / devicecontrol(终端管理) / more(更多功能)

more = [
  deviceinfo        路由器信息
  upgrade           升级
  netsettings       网络设置
    ├ lan           局域网
    ├ vpn           VPN（PPTP / L2TP / 隧道）
    ├ alg           ALG
    ├ iptv          IPTV
    ├ upnp          UPnP
    ├ wlanintelligent  智联
    └ ipv6          IPv6
  wifisettings      Wi-Fi 设置
    ├ wlanadvance   Wi-Fi 高级
    ├ wlanguardrubnet  防蹭网
    ├ wlanguest     访客网络
    ├ repeater      中继
    ├ wlaneco       Wi-Fi 节能
    └ wps           WPS
  remoteset(url:ddns)  远程访问
  safesettings      安全设置
    ├ remote        远程管理
    ├ firewall      防火墙
    ├ nat           NAT 服务（端口映射/触发/DMZ）
    └ dmz           DMZ
  systemsettings    系统设置
    ├ account       账号
    ├ sntp          时间
    ├ ntwkportrate  网口速率
    ├ reset         恢复出厂
    ├ diagnose      诊断
    ├ mirror        端口镜像
    └ wasuprivacy   隐私
  application       应用
    ├ smartpush     推送
    └ userbehavior  用户体验计划
]
```

**文案包路径**：`/lang/zh/{name}_res.js`，`name` 取上表 id（如 `/lang/zh/wlanguest_res.js`）。
已下载 72 份在 `.tmp-render/fw/lang/`。

---

## 6. 已知风险与已澄清的问题

### 6.1 `ntwk/wlanfilterenhance` 的 404（**已澄清：偶发节流，字段名正确**）

第一次批量抓取时这个接口返回 404，一度怀疑需要一个特殊请求头。做了受控实验
（4 种请求头组合 × 13 个接口，见 `.tmp-render/fw-live/header-matrix.json`）：

| 组合 | wlanfilterenhance | urlfilter | timecontrol |
|---|---|---|---|
| 裸 GET（无任何额外头） | **200** | 200 | 404 |
| 带 `X-Requested-With` | 200 | 200 | 404 |
| 带 CSRF 头 | 200 | 200 | 404 |
| 两者都带 | 200 | 200 | 404 |

**结论：与请求头无关，裸 GET 就能拿到。** 第一次的 404 是**连续快速请求被固件节流**导致的偶发
（当时 107 个请求 × 250ms 间隔；同时段部分接口 200、部分 404，交替出现，不是会话失效）。
批量抓取时若偶发 404，重试一次即可。

#### 真实返回结构（`GET`，数组长度 2 = 2.4G + 5G）

```jsonc
[
  {"MACAddressControlEnabled": true,
   "MacFilterPolicy": 0,
   "ID": "InternetGatewayDevice.X_Config.Wifi.Radio.1.Ssid.1.",
   "FrequencyBand": "2.4GHz",
   "WMACAddresses": [{"MACAddress":"AA:BB:CC:DD:EE:FF","HostName":"电视盒子A"}, ...],
   "BMACAddresses": []},
  {"MACAddressControlEnabled": true, "MacFilterPolicy": 0,
   "ID": "InternetGatewayDevice.X_Config.Wifi.Radio.2.Ssid.1.",
   "FrequencyBand": "5GHz",
   "WMACAddresses": [ ... ], "BMACAddresses": []}
]
```

- ✅ 字段名就是 **`WMACAddresses` / `BMACAddresses`**（全大写 W/B + Addresses）。
  固件 JS 里的 `WMacFilters` / `BMacFilters` 是前端 UI 的临时变量名，**不是 API 字段**，别混。
- **`MacFilterPolicy` 语义（关键）**：
  - `0` = **黑名单模式**（名单里的设备被禁止）—— 真机出厂默认
  - `1` = **白名单模式**（只有名单里的设备能连）
  - 判定依据（固件 `c-37.js`）：`1 == MacFilterPolicy && WhiteMacList.length == 0` 时弹
    「没有白名单设备」提示；`0 == MacFilterPolicy` 时删除设备会同时清理黑/白两个名单。
  - ⚠️ **白名单模式下往 `BMACAddresses` 加设备，固件会忽略**。
    本程序已加拦截（`set_host_blacklist` 检查 policy，是白名单模式就拒绝并提示）。
- **`MacFilterCapacity` 真机 = 256**（不是从 JS 推断的 32）；且容量只约束白名单
  （`MacFilterPolicy && (...)`），黑名单是另一套上限。
- 真机当前状态：总开关 `true`、`MacFilterPolicy: 0`、白名单各 4 条、黑名单空
  → **本程序的黑名单功能在这台机器上可直接使用**。

### 6.2 404 但功能存在的接口（改名残留）

`portforwarding` → 实际用 `portmapping`；`multiwan` → 实际用 `manywan` / `doublewan`；
`dt` 类旧名同理。路由表里同时留着新旧两套名字，只有新名字能用。

### 6.3 字段名陷阱

- `diaplayName`（ethnegotiation）—— 固件拼写错误
- `FristIP`（lan / lan_host）—— 固件拼写错误（First）
- `FristIP` / `FirstMac` 在 `lan_host` 里类型不一致（`FirstMac` 实际是子网掩码 `255.255.255.0`）
- `BackupStatus` / `Backupflag` 大小写不统一

### 6.4 隐私字段（**绝不能进日志或界面**）

`Username`（宽带账号，明文）、`SN`、`SerialNumber`、`uuid`、`devId`、`enDevId`、
`NetAccessCode`、`Password`/`Pwd`/`PppPass`/`TunnelPassword`、`WifiSsidFactory`、
`MacAddress`/`MACAddress`、`IPAddress`、`IPv6Address`、`HostName`（用户设备名）。

---

## 7. 对 HiRouterCenter 的扩展建议（按性价比排序）

| 想法 | 数据来源 | 成本 | 说明 |
|---|---|---|---|
| **设备卡显示协商速率** | `HostInfo.rate` | 低 | 有线 2500 → 「有线 · 2.5G」；无线 433 → 「5G · 433M」 |
| **设备卡显示信号强度** | `HostInfo.rssi` | 低 | 无线才有，可做信号格 |
| **静态 IP 绑定管理** | `lan_ipaddressreserve` | 中 | 读 + POST 整数组 |
| **有线口状态卡片** | `ethnegotiation` | 低 | LAN1-4 / WAN 各口速率与连接状态 |
| **诊断：ping / 网页测试** | `system/diagnose_ping`、`httpdiagnose` | 中 | 有副作用（会真的发诊断），需用户确认 |
| **测速** | `app/speedtest` | 中 | 读结果容易，触发测速要 POST |
| **Wi-Fi 信道优化** | `channelinfo` + `isSupportQueryAndSetChannel` | 高 | 有评分数据，但改信道风险高 |
| **访客网络** | `wlanguest` 语言包 + `guest_network_limitrate` | 中 | 配置接口 404，需再取证 |
| **IPTV 口设置** | `iptv` | 中 | 读容易，写影响有线口用途 |
| **端口映射** | `portmapping` | 中 | 读容易（当前空） |
| **系统信息页** | `deviceinfo` + `sntp` + `wandetect` | 低 | 纯展示 |
| **上网时长/流量统计** | `RxKBytes`/`TxKBytes` + `AccessRecord` | 低 | 只能拿到累计值，做不了时间段统计 |
| **端口镜像** | `modcap` 未列，`ntwk/mirror` 404 | — | 不支持 |
| **网址过滤** | `modcap.support_urlflt=0` | — | 不支持 |
| **NFC 一碰连** | `modcap.isSupportNFC=0` | — | 不支持 |

---

## 8. 文件索引

| 路径 | 内容 | 进仓库 |
|---|---|---|
| `tools/firmware-probe/routes.json` | **171 条 API 路由表**（key → path） | ✅ |
| `tools/firmware-probe/fetch-list.json` | 抓取清单（107 可读 + 64 跳过及原因） | ✅ |
| `tools/firmware-probe/*.js` | 四个抓取脚本（见该目录 README） | ✅ |
| `docs/firmware-api.md` | 本文件 | ✅ |
| `.tmp-render/fw/main.js` | 固件主包（路由表、菜单树、store） | ✗ |
| `.tmp-render/fw/c-*.js` | 43 个懒加载 chunk（各功能页实现 1.6MB） | ✗ |
| `.tmp-render/fw/lang/*.js` | 72 份中文文案包（功能名/提示语 159KB） | ✗ |
| `.tmp-render/fw-live/api/*.json` | **56 个接口的真机原始返回**（含隐私） | ✗ |
| `.tmp-render/fw-live/schema.json` | 56 接口 × 460 字段的脱敏结构 | ✗ |
| `.tmp-render/fw-live/crawl-index.json` | 抓取结果索引（状态码/大小） | ✗ |
| `.tmp-render/fw-live/reprobe.json` | 404 接口复探结果 | ✗ |
| `.tmp-render/fw-live/header-matrix.json` | 请求头矩阵实验结果 | ✗ |

**重新采集**（脚本已随仓库提供，不需要再去翻 `.tmp-render`）：

```bash
export NODE_PATH=/c/Users/Jun/.workbuddy/binaries/node/workspace/node_modules
node tools/firmware-probe/fw-crawl.js      # 浏览器弹出后手动登录
```

`.tmp-render/` 被 `.gitignore` 排除，清理工作副本不会影响脚本与路由表（它们在 `tools/`）。

---

## 附录 A：171 条路由的可用性总表

真机实测：**✅ 可用 56 条 / ❌ 本机型无 51 条 / 🚫 主动跳过 64 条**。

> 🚫 = 有副作用（重启/升级/恢复出厂/上传/改密/诊断/扫描/上报），取证时故意不发请求。
> 这些接口**不是不可用**，只是没验证；要用请先确认后果。

### A.1 可用（GET 返回 200）

| key | 路径 | 状态 | 备注 |
|---|---|---|---|
| `HostInfo` | `system/HostInfo` | ✅ |  |
| `application` | `app/application` | ✅ | 空 |
| `applicationitems` | `app/applicationitems` | ✅ | 空 |
| `backhaul` | `ntwk/backhaul` | ✅ |  |
| `channelinfo` | `ntwk/channelinfo` | ✅ |  |
| `ddns` | `ntwk/ddns` | ✅ |  |
| `ddnsstatus` | `ntwk/ddnsstatus` | ✅ |  |
| `device_count` | `system/device_count` | ✅ |  |
| `deviceinfo` | `system/deviceinfo` | ✅ |  |
| `dmz` | `ntwk/dmz` | ✅ |  |
| `doublewan` | `ntwk/wan` | ✅ |  |
| `encpubkey` | `system/encpubkey` | ✅ |  |
| `ethnegotiation` | `ntwk/ethnegotiation` | ✅ |  |
| `firewall` | `ntwk/firewall` | ✅ |  |
| `forceupgcfg` | `system/forceupgcfg` | ✅ |  |
| `getmacaddress` | `ntwk/getmacaddress` | ✅ |  |
| `guest_network_limitrate` | `ntwk/guest_network_limitrate` | ✅ |  |
| `hilink_status` | `hilink/hilink_status` | ✅ |  |
| `homesec_stealnet` | `ntwk/homesec_stealnet` | ✅ |  |
| `ip6firewall_enable` | `ntwk/ip6firewall_enable` | ✅ |  |
| `ip6firewall_trustlist` | `ntwk/ip6firewall_trustlist` | ✅ |  |
| `iptv` | `ntwk/iptv` | ✅ |  |
| `ipv6_enable` | `ntwk/ipv6_enable` | ✅ |  |
| `ipv6_lan` | `ntwk/ipv6_lan` | ✅ |  |
| `ipv6_wan` | `ntwk/ipv6_wan` | ✅ |  |
| `l2tp` | `ntwk/l2tp` | ✅ |  |
| `lan` | `ntwk/lan` | ✅ |  |
| `lan_all` | `ntwk/lan_all` | ✅ |  |
| `lan_host` | `ntwk/lan_host` | ✅ |  |
| `lan_ipaddressreserve` | `ntwk/lan_ipaddressreserve` | ✅ |  |
| `lan_server` | `ntwk/lan_server` | ✅ |  |
| `lan_upnp` | `ntwk/lan_upnp` | ✅ |  |
| `lan_upnp_portmapping` | `ntwk/lan_upnp_portmapping` | ✅ | 空 |
| `ledstatus` | `hilink/ledstatus` | ✅ |  |
| `location` | `system/location` | ✅ |  |
| `manywan` | `ntwk/wan` | ✅ |  |
| `onlinestate` | `system/onlinestate` | ✅ |  |
| `portmapping` | `ntwk/portmapping` | ✅ | 空 |
| `porttrigger` | `ntwk/porttrigger` | ✅ | 空 |
| `pptp` | `ntwk/pptp` | ✅ |  |
| `privacypolicy` | `app/privacypolicy` | ✅ |  |
| `repeaterstate` | `ntwk/repeaterstate` | ✅ |  |
| `slavedevinfo` | `hilink/slavedevinfo` | ✅ | 空 |
| `sntp` | `ntwk/sntp` | ✅ |  |
| `speedtest` | `app/speedtest` | ✅ |  |
| `timedredial` | `ntwk/timedredial` | ✅ |  |
| `topology` | `device/topology` | ✅ |  |
| `urlfilter` | `ntwk/urlfilter` | ✅ | 空 |
| `wandetect` | `ntwk/wandetect` | ✅ |  |
| `wansearchcontrol` | `ntwk/wansearchcontrol` | ✅ |  |
| `wlandbho` | `ntwk/wlandbho` | ✅ |  |
| `wlanintelligent` | `ntwk/wlanintelligent` | ✅ |  |
| `wlanmode` | `system/wlanmode` | ✅ |  |
| `wlanradio` | `ntwk/wlanradio` | ✅ |  |
| `wlantimeaccelerate` | `ntwk/wlanTimingAccelerate` | ✅ |  |
| `wlanwifisync` | `ntwk/wlanwifisync` | ✅ |  |

### A.2 本机型没有（GET 404，功能确实不存在或已改名）

| key | 路径 | 状态 | 备注 |
|---|---|---|---|
| `MultiHostInfo` | `system/MultiHostInfo` | ❌ |  |
| `RepeaterDial` | `ntwk/RepeaterDial` | ❌ |  |
| `RepeaterDial_scram` | `ntwk/RepeaterDial_scram` | ❌ |  |
| `WlanTestStatus` | `ntwk/WlanTestStatus` | ❌ |  |
| `aichanoptinfo` | `ntwk/aichanoptinfo` | ❌ |  |
| `alg` | `ntwk/alg` | ❌ |  |
| `app_wizard` | `app/wizards` | ❌ |  |
| `aria2Infos` | `openee/plugin/infos` | ❌ |  |
| `country_code` | `ntwk/country_code` | ❌ |  |
| `dms` | `app/dms` | ❌ |  |
| `ethportmode` | `app/ethportmode` | ❌ |  |
| `fsstatus` | `usbstorage/fsstatus` | ❌ |  |
| `fwmacfilter` | `ntwk/fwmacfilter` | ❌ |  |
| `getpairstatus` | `ntwk/getpairstatus` | ❌ |  |
| `guest_network_resttime` | `ntwk/guest_network_resttime` | ❌ |  |
| `hilinkwaninfo` | `ntwk/hilinkwaninfo` | ❌ |  |
| `l2topo` | `device/l2topo` | ❌ |  |
| `lan_devicetype` | `ntwk/lan_devicetype` | ❌ |  |
| `lan_ipserverpool` | `ntwk/lan_ipserverpool` | ❌ |  |
| `language` | `language/lang` | ❌ |  |
| `main_router_ssid` | `ntwk/main_router_ssid` | ❌ |  |
| `mcast` | `ntwk/mcast` | ❌ |  |
| `mirror` | `ntwk/mirror` | ❌ |  |
| `multi_bridge_wan` | `ntwk/multi_bridge_wan` | ❌ |  |
| `multi_ssid` | `ntwk/multi_ssid` | ❌ |  |
| `multiwan` | `ntwk/multiwan` | ❌ |  |
| `nfc_switch` | `bsp/nfc_switch` | ❌ |  |
| `ntwkcap_compare` | `hilink/ntwkcap_compare` | ❌ |  |
| `online_check` | `system/online_check` | ❌ |  |
| `plc_web_switch_siso` | `ntwk/plc_web_switch_siso` | ❌ |  |
| `plcenableall` | `ntwk/plcenableall` | ❌ |  |
| `portforwarding` | `ntwk/portforwarding` | ❌ |  |
| `powernetwork` | `ntwk/powernetwork` | ❌ |  |
| `qos` | `app/qos` | ❌ |  |
| `repeaterinfo` | `ntwk/repeaterinfo` | ❌ |  |
| `sambaanonymous` | `usbstorage/sambaanonymous` | ❌ |  |
| `sdcapacity` | `sdcard/sdcapacity` | ❌ |  |
| `smartpush_autoupg` | `app/smartpush_autoupg` | ❌ |  |
| `smartvpn` | `ntwk/smartvpn` | ❌ |  |
| `smartvpnmaclist` | `ntwk/smartvpnmaclist` | ❌ |  |
| `smartvpnurl` | `ntwk/smartvpnurl` | ❌ |  |
| `tgpgameinfo` | `app/tgpgameinfo` | ❌ |  |
| `tgpgameswitch` | `app/tgpgameswitch` | ❌ |  |
| `tunnel` | `ntwk/tunnel` | ❌ |  |
| `tunneltype` | `ntwk/tunneltype` | ❌ |  |
| `urlsec` | `ntwk/urlsec` | ❌ |  |
| `wanlearntrigerloopmac` | `ntwk/wanlearntrigerloopmac` | ❌ |  |
| `wlan_easymesh` | `ntwk/wlan_easymesh` | ❌ |  |
| `wlanelink` | `ntwk/wlanelink` | ❌ |  |
| `wlanwps` | `ntwk/wlanwps` | ❌ |  |
| `wps_switch` | `ntwk/wps_switch` | ❌ |  |

### A.3 主动跳过（有副作用，未验证）

| key | 路径 | 状态 | 备注 |
|---|---|---|---|
| `access_auth` | `ntwk/access_auth` | 🚫 |  |
| `andlink_lock_net` | `ntwk/andlink_lock_net` | 🚫 |  |
| `aria2_upload` | `sdcard/fileupload` | 🚫 |  |
| `autoupgrade` | `system/autoupgrade` | 🚫 |  |
| `bi_statistics` | `system/bi_statistics` | 🚫 |  |
| `changedevicename` | `system/changedevicename` | 🚫 |  |
| `client_heartbeat` | `ntwk/client_heartbeat` | 🚫 |  |
| `custom_report` | `system/custom_report` | 🚫 |  |
| `delayreboot` | `system/delayreboot` | 🚫 |  |
| `deletefile` | `sdcard/deletefile` | 🚫 |  |
| `diagnose_button` | `system/diagnose_button` | 🚫 |  |
| `diagnose_crash` | `system/diagnose_crash` | 🚫 |  |
| `diagnose_crash_devlist` | `system/diagnose_crash_devlist` | 🚫 |  |
| `diagnose_led` | `system/diagnose_led` | 🚫 |  |
| `diagnose_ping` | `system/diagnose_ping` | 🚫 |  |
| `diagnose_usb` | `system/diagnose_usb` | 🚫 |  |
| `dnsdiagnose` | `system/dnsdiagnose` | 🚫 |  |
| `forceupg` | `system/forceupg` | 🚫 |  |
| `forceupglater` | `system/forceupglater` | 🚫 |  |
| `guide` | `system/guide` | 🚫 |  |
| `guideheartbeat` | `system/guideheartbeat` | 🚫 |  |
| `heartbeat` | `system/heartbeat` | 🚫 |  |
| `homesec_abfa` | `ntwk/homesec_abfa` | 🚫 |  |
| `hota_redirect_omit` | `system/hota_redirect_omit` | 🚫 |  |
| `hotaservice` | `system/hotaservice` | 🚫 |  |
| `httpdiagnose` | `system/httpdiagnose` | 🚫 |  |
| `ip_capture` | `ntwk/ipcapture` | 🚫 |  |
| `onlineupg` | `system/onlineupg` | 🚫 |  |
| `plc_web_certification` | `ntwk/plc_web_certification` | 🚫 |  |
| `processstatus` | `system/processstatus` | 🚫 |  |
| `provcode` | `system/provcode` | 🚫 |  |
| `pwd` | `system/pwd` | 🚫 |  |
| `pwdrule` | `system/pwdrule` | 🚫 |  |
| `qosclass_host` | `app/qosclass_host` | 🚫 |  |
| `rebootplan` | `system/rebootplan` | 🚫 |  |
| `repeaterdiag` | `ntwk/repeaterdiag` | 🚫 |  |
| `restorestate` | `system/restorestate` | 🚫 |  |
| `sdfile` | `sdcard/sdfile` | 🚫 |  |
| `slave_setup` | `hilink/slave_setup` | 🚫 |  |
| `swan` | `ntwk/swan` | 🚫 |  |
| `timecontrol` | `ntwk/timecontrol` | 🚫 |  |
| `tr069` | `app/tr069` | 🚫 |  |
| `uploadconfigfile` | `device/uploadconfigfile` | 🚫 |  |
| `uploadconfigfileresult` | `device/uploadconfigfileresult` | 🚫 |  |
| `uploadimage` | `device/uploadimage` | 🚫 |  |
| `usbaccount` | `usbstorage/usbaccount` | 🚫 |  |
| `usbchangemode` | `system/usbchangemode` | 🚫 |  |
| `user_login` | `system/user_login` | 🚫 |  |
| `user_login_nonce` | `system/user_login_nonce` | 🚫 |  |
| `user_login_proof` | `system/user_login_proof` | 🚫 |  |
| `user_logout` | `system/user_logout` | 🚫 |  |
| `useraccount` | `system/useraccount` | 🚫 |  |
| `useraccount_scram` | `system/useraccount_scram` | 🚫 |  |
| `userbehavior` | `system/userbehavior` | 🚫 |  |
| `wandiagnose` | `ntwk/wandiagnose` | 🚫 |  |
| `wifiscan` | `ntwk/wifiscan` | 🚫 |  |
| `wifiscanresult` | `ntwk/wifiscanresult` | 🚫 |  |
| `wizard_wifi` | `system/wizard_wifi` | 🚫 |  |
| `wlan_time_switch_list` | `ntwk/wlan_time_switch_list` | 🚫 |  |
| `wlanfilterenhance` | `ntwk/wlanfilterenhance` | 🚫 |  |
| `wlanpowertimeswitch` | `ntwk/wlanpowertimeswitch` | 🚫 |  |
| `wlantimeswitch` | `ntwk/wlantimeswitch` | 🚫 |  |
| `xlink_lock_net` | `ntwk/xlink_lock_net` | 🚫 |  |
| `zjct_redirect` | `ntwk/zjct_redirect` | 🚫 |  |

---

## 附录 B：功能页语言包索引

文案包路径 `/lang/zh/{name}_res.js`，已下载 72 份在 `.tmp-render/fw/lang/`。

| 模块名 | 文案条数 | 代表文案 |
|---|---|---|
| `account` | 12 | 修改登录密码 |
| `alg` | 5 | ALG 设置 |
| `ddns` | 16 | 动态域名服务 DDNS |
| `deviceinfo` | 37 | 路由器信息 |
| `devices` | 41 | 有线连接设备 |
| `diagnose` | 50 | 诊断 |
| `dmz` | 4 | DMZ 主机 |
| `firewall` | 27 | 防火墙 |
| `forceupg` | 11 | {0}升级提醒 |
| `home` | 33 | SSID： |
| `internet` | 68 | 服务名 |
| `iptv` | 52 | IPTV 设置 |
| `lan` | 58 | 局域网 |
| `repeater` | 19 | Wi-Fi 中继 |
| `reset` | 13 | 备份与恢复 |
| `sntp` | 117 | 网络时间 |
| `upgrade` | 36 | 升级管理 |
| `vuex` | 518 | 宽带帐号 |
| `wifi` | 46 | Wi-Fi |
| `wlanadvance` | 38 | Wi-Fi 高级 |
| `wlanauthorizeredirect` | 2 | 连网提示 |
| `wlanguest` | 23 | 客人 Wi-Fi |
| `wlanintelligent` | 24 | 智联设置 |

---

## 附录 C：56 个可用接口的字段名清单

> 只列**字段名与类型**，不列真实值（值见 `.tmp-render/fw-live/api/`，不进仓库）。
> `arr[n]` = 数组，括号内是元素字段；`obj` = 对象。

| 接口 | 形状 | 字段 |
|---|---|---|
| `HostInfo` | `arr[37]` | ID:str, MACAddress:str, IsSetupSlave:bool, HiLinkDevice:bool, IsSupportNoManage:int, HiLinkDevHide:bool, IPAddress:str, Active:bool, Active46:bool, WlanActive:bool, IsSlave:bool, SerialNumber:str, ShowDeviceRealRate:int, UpRate:int, DownRate:int, AccessRecord:str, OfflineRecord:str, TxKBytes:str, RxKBytes:str, IPv6Address:str, V6Active:bool, IconType:str, ActualName:str, domain:str, HostName:str, InterfaceType:str, Layer2Interface:str, AddressSource:str, LeaseTime:str, PhyType:int, VendorClassID:str, hwtypeoptionnew:bool, DevBrands:str, Frequency:str, IsGuest:bool, MacFilterID:str, ParentControlEnable:bool, ParentControl:bool, DeviceDownRateEnable:bool, QosclassID:str, PolicerID:str, ClassQueue:int, ActualManu:str, ActualType:str, ProdId:str, Feature:int, rate:int, rssi:int, NearlinkStat:int, devId:str, roomName:str, supportAbility:int, roomId:int, DeviceMaxUpLoadRate:int, DeviceMaxDownLoadRate:int, Ipv6Addrs:list |
| `application` | `arr[0]` | *（空）* |
| `applicationitems` | `arr[0]` | *（空）* |
| `backhaul` | `obj` | pwd:str |
| `channelinfo` | `obj` | HideChannelMode:int, NetStatus:int, WifiStatus:list, ChannelDeploy:int, NetChannelMode:int |
| `ddns` | `obj` | Provider:str, Username:str, Password:str, Protocol:str, HostName:str, Status:str, Domain:str, Enable:bool, Port:str, Server:str |
| `ddnsstatus` | `obj` | Status:str, ConnectType:str, Enable:bool |
| `device_count` | `obj` | LanActiveNumber:int, HiLinkDevNum:int, UserNumber:int, ActiveDeviceNumbers:int |
| `deviceinfo` | `obj` | HardwareVersion:str, ManufacturerOUI:str, ManufacturerId:str, UpTime:int, SNHashType:int, UpgradeTime:int, custinfo:obj, SkuType:int, modcap:obj, FriendlyName:str, NtwkCapScore:int, devcap:obj, centralCap:str, EmuiVersion:str, RouterType:str, HarmonyOSVersion:str, DeviceIconType:str, WeeklyReportUrl:str, NetAccessCode:str, csrf_param:str, csrf_token:str, NetType:int, NetECCode:str, uuid:str, MacFilterCapacity:int, DeviceName:str, SerialNumber:str, other:obj, backupflag:int, SoftwareVersion:str, SmartDevInfo:obj |
| `dmz` | `obj` | Enable:bool, HostIPAddress:str, IPAddress:str, HostName:str |
| `doublewan` | `arr[4]` | PPPDialIpMode:str, PPPDialIpAddr:str, Name:str, Alias:str, UpBandwidth:int, Enable:bool, AccessType:str, MACColoneEnable:bool, WanType:str, ConnectionStatus:str, X_SpeDialMode:int, Username:str, ServiceList:str, MRU:int, MTU:int, PPPAuthMode:str, MSS:int, PPPTrigger:str, NATType:int, IPv4AddrType:str, IPv4Enable:bool, IPv4Addr:str, ID:str, IPv4Mask:str, IPv4Gateway:str, IPv4DnsServers:str, DNSOverrideAllowed:bool, IPv6Enable:bool, IPv6AddrType:str, IPv6Addr:str, AccessStatus:str, IPv6Gateway:str, IPv6DnsServers:str, IsConfigured:int, IPv6PrefixList:str, UpBandwidthHistory:str, LowerLayer:str, DownBandwidthHistory:str, BandwidthTime:str, UpBandwidthMax:int, IsDefault:int, DownBandwidthMax:int, DownBandwidth:int, PPPoEACName:str, PPPoEServiceName:str, IPv6AddrPrefixLen:int, IPv6AddrSet:str, PPPIdletime:int, Password:str, ConnectionType:str, MACColone:str, IPv6ConnectionStatus:str |
| `encpubkey` | `obj` | EncpubkeyE:str, EncpubkeyN:str |
| `ethnegotiation` | `obj` | ethintflist:list |
| `firewall` | `obj` | ArpAttack:bool, CurrentLevel:str, SetLevel:str, SynFlooding:bool, IcmpFlooding:bool |
| `forceupgcfg` | `obj` | EndTime:str, Enable:bool, StartTime:str |
| `getmacaddress` | `obj` | macaddress:str, ipaddress:str |
| `guest_network_limitrate` | `obj` | PeakRate:int, X_DownPeakRate:int, phyType:int, Enable:int |
| `hilink_slavedevinfo` | `arr[0]` | *（空）* |
| `hilink_status` | `obj` | hilink_status:int |
| `homesec_stealnet` | `obj` | AntiLeakageCapability:bool, StealNetModel:int, Info:obj |
| `ip6firewall_enable` | `obj` | Enable:bool |
| `ip6firewall_trustlist` | `arr[1]` | Name:str, RemoteIp:str, LocalIp:str, ID:str, Port:int |
| `iptv` | `obj` | AutoBindEnable:bool, SlaveList:list, PortNum:int, FixWanPort:int, VLANEnable:bool, VLANMode:str, Enable:bool, AccessType:str, VLANId:int, VLAN1p:int, PVC:str, LANAlias:str, SnoopingEnable:bool, ProxyEnable:bool, ProxyWan:str, ConnectionType:str, WANPath:str |
| `ipv6_enable` | `obj` | ID:str, Enable:int |
| `ipv6_lan` | `obj` | WanLinkAddr:str, SLAAC:obj, LanLinkAddr:str, DHCP6s:obj |
| `ipv6_wan` | `obj` | X_IPv6DNSServerOne:str, X_IPv6DNSServerTwo:str, X_IPv6PrefixLength:int, X_IPv6AddressingType:str, X_IPv6Address:str, X_IPv6DefaultGateway:str, ID:str, X_IPv6DNSOverrideAllowed:bool, X_IPv6IsAutoConfig:bool, X_IPv6DNSEnabled:bool |
| `l2tp` | `obj` | TunnelPassword:str, KeepAliveTime:int, PrimaryDNSServer:str, SecondaryDNSServer:str, WanInterface:str, HostName:str, PPPPassword:str, ConnectionMode:str, LocalIPAddress:str, Errinfo:str, PPPUsername:str, LACEnable:bool, LNSAddress:str, ConnectionStatus:str |
| `lan` | `obj` | dhcpID:str, MinIP:str, MaxIP:str, LNSAddr:str, SourceIP:str, FristIP:str, FirstMac:str, DomainName:str, DevName:str, ID:str, FullName:str |
| `lan_all` | `arr[2]` | ID:str, IPInterfaceIPAddress:str, IPInterfaceSubnetMask:str |
| `lan_host` | `obj` | FirstEnable:bool, ShowLanDomainEnable:bool, FristIP:str, FirstMac:str, DomainName:str, DevName:str, ID:str, LNSAddr:str, MACAddress:str |
| `lan_ipaddressreserve` | `arr[4]` | ID:str, Chaddr:str, Yiaddr:str, Enable:bool |
| `lan_server` | `obj` | MinIP:str, MaxIP:str, UseAllocatedWAN:str, ServerEnable:bool, DNSServerone:str, DNSServertwo:str, AssociatedConnection:str, PassthroughMACAddress:str, PassthroughLease:int, ID:str, dnsmode:str, DHCPLeaseTime:int |
| `lan_upnp` | `obj` | enable:bool |
| `lan_upnp_portmapping` | `arr[0]` | *（空）* |
| `ledstatus` | `obj` | ErrorCategory:str, Status:int, SearchSatelliteDuration:int, Mac:str |
| `location` | `obj` | isRemote:bool |
| `manywan` | `arr[4]` | UpBandwidthHistory:str, IsConfigured:int, Name:str, Alias:str, Enable:bool, AccessType:str, MACColoneEnable:bool, ConnectionType:str, ConnectionStatus:str, X_SpeDialMode:int, Username:str, ServiceList:str, MRU:int, MTU:int, PPPAuthMode:str, MSS:int, PPPTrigger:str, NATType:int, IPv4AddrType:str, IPv4Enable:bool, IPv4Addr:str, ID:str, IPv4Mask:str, IPv4Gateway:str, IPv4DnsServers:str, DNSOverrideAllowed:bool, IPv6Enable:bool, IPv6AddrType:str, IPv6Addr:str, AccessStatus:str, IPv6Gateway:str, WanType:str, IPv6DnsServers:str, IPv6ConnectionStatus:str, IPv6PrefixList:str, Password:str, LowerLayer:str, IsDefault:int, PPPIdletime:int, IPv6AddrSet:str, PPPDialIpMode:str, IPv6AddrPrefixLen:int, PPPDialIpAddr:str, PPPoEACName:str, PPPoEServiceName:str, DownBandwidth:int, UpBandwidth:int, MACColone:str, DownBandwidthMax:int, UpBandwidthMax:int, BandwidthTime:str, DownBandwidthHistory:str |
| `ntwk_urlfilter` | `arr[0]` | *（空）* |
| `ntwk_wlan_time_switch_list` | `obj` | maclist:list |
| `ntwk_wlanfilterenhance` | `arr[2]` | MACAddressControlEnabled:bool, MacFilterPolicy:int, ID:str, FrequencyBand:str, WMACAddresses:list, BMACAddresses:list |
| `onlinestate` | `obj` | DeviceType:str, IpAddress:str, custinfo:obj, CurrentVersion:str, SN:str, Cookie:str, Version:str, UpgradeContent:str, DeviceName:str, UpdateState:int, ImageSize:int, DownloadSize:int, IsMainDevice:bool, UpgTimes:int, CurrentUpgradeTime:str, CurrentChangeLog:str, DevId:str, IsSupportOnlineUpg:int, IsSupportGUI:int, URL:str, DownloadProcess:int |
| `portmapping` | `arr[0]` | *（空）* |
| `porttrigger` | `arr[0]` | *（空）* |
| `pptp` | `obj` | ENABLE:bool, WanInterface:str, ServerAddress:str, TunnleAddress:str, PppUser:str, PppPass:str, ConnectionMode:str, PrimaryDNSServer:str, SecondaryDNSServer:str, Errinfo:str, ConnectionStatus:str |
| `privacypolicy` | `obj` | IsEULAUpdate:int, EULAUrl:str, ChangeStatus:int, PIPAVersion:int, ChangedFeature:str, IsPrivacyPolicyUpdate:int, privacyApproveVersion:str, PrivacyPolicyUrl:str, privacyVersion:str, EULAVersion:str, personalDataVersion:str |
| `repeaterstate` | `obj` | bssid:str, connstate:str, signal:str, channel:str, speed:str, ssid:str, Wlan24SSID:str, Wlan5SSID:str, radio:str, wifiConnectState:int, WifiSsidFactory:str |
| `slavedevinfo` | `arr[0]` | *（空）* |
| `sntp` | `obj` | NTPServer2:str, Status:str, SntpVersion:int, SntpIsSynchronizedStatus:bool, LocalTimeZoneName:str, TimeZoneIdx:int, CurrentLocalTime:str, NTPServer1:str |
| `speedtest` | `obj` | SpeedtestResult:int, SpeedtestStatus:int, DownBandwidth:int, UpBandwidth:int |
| `system_device_count` | `obj` | HiLinkDevNum:int, UserNumber:int, ActiveDeviceNumbers:int, LanActiveNumber:int |
| `timedredial` | `obj` | RedialTime:str, Enable:bool |
| `topology` | `arr[5]` | ConnectedDevices:list, Active:bool, HiLinkType:str, Name:str, MACAddress:str |
| `urlfilter` | `arr[0]` | *（空）* |
| `wandetect` | `obj` | DefaultGateway:str, DNSServers:str, IPv6Enable:bool, DetailErr:str, AccessStatus:str, SearchingStatus:str, IPv6Address:str, AccessType:str, IPv6DefaultGateway:str, IPv6PrefixList:str, ConnectionStatus:str, IPv6ConnectionStatus:str, IPv6AddressingType:str, ConnectionType:str, ExternalIPAddress:str, AutoFlag:str, BackupStatus:int, ErrReason:str, Uptime:int, IPv6PrefixLength:int, Status:str, IPv4Enable:bool, HttpStatus:int, ID:str, IPv6DNSServers:str, WanResult:str, PVCResult:str |
| `wansearchcontrol` | `obj` | Enable:bool, WanInterface:str |
| `wlandbho` | `obj` | MloEnable:bool, DbhoEnable:bool |
| `wlanintelligent` | `obj` | ID:str, enable:bool, ntwksyncEnable:bool |
| `wlanmode` | `obj` | ConnectState:str, EmRouterRole:int, HilinkStatus:int, WLANMode:int |
| `wlanradio` | `obj` | Enable5G:bool, Enable2G:bool, InitEnable2G:bool, PowerMode:int, InitEnable5G:bool, PowerModeChgTip:bool, WLANMode:int |
| `wlantimeaccelerate` | `obj` | AccelerateTime:str, Records:list, Enable:bool |
| `wlanwifisync` | `obj` | WifisyncStatus:bool, wifiPowerStatus:bool |
