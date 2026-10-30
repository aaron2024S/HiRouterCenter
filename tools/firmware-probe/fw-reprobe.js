/* 404 接口复探 v4：登录后对抓取失败的关键接口做多种 GET 变体，
   确认是「本机型不支持」还是「需要参数/不同形态」。
   绝不发 POST（避免误改配置）。 */
const { chromium } = require("playwright-core");
const fs = require("fs");
const path = require("path");

const OUT = path.join(__dirname, "..", "..", ".tmp-render", "fw-live");
const EDGE = process.env.HRC_EDGE || "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe";
const BASE = process.env.HRC_ROUTER || "http://192.168.3.1";
const stamp = () => new Date().toISOString().slice(11, 19);
const log = (...a) => console.log(stamp(), ...a);

/* 要复探的接口：本程序未来的候选功能 + 已知 404 的重点项 */
const TARGETS = [
  "ntwk/wlanfilterenhance",   // 黑名单（程序中在用！）
  "app/qos",                  // QoS
  "ntwk/portforwarding",      // 端口转发
  "ntwk/urlfilter",           // 网址过滤
  "ntwk/multi_ssid",          // 多 SSID
  "ntwk/tunnel",              // 隧道
  "ntwk/smartvpn",            // 智能 VPN
  "ntwk/fwmacfilter",         // MAC 过滤（旧）
  "ntwk/wlanwps",             // WPS
  "ntwk/wlan_easymesh",       // 智联
  "ntwk/wlanelink",           // elink
  "ntwk/urlsec",              // 网址安全
  "ntwk/mcast",               // 组播
  "ntwk/mirror",              // 端口镜像
  "ntwk/portforwarding?",     // 占位
  "hilink/slavedevinfo",      // 子设备信息
  "device/l2topo",            // 二层拓扑
  "system/online_check",      // 在线检测
  "system/device_count",      // 设备计数
  "ntwk/timecontrol",         // 上网时间控制
  "ntwk/guest_network_resttime",
  "ntwk/wlan_time_switch_list",
  "ntwk/tgpgameinfo",
];

const VARIANTS = [
  { tag: "plain", q: "" },
  { tag: "type=all", q: "?type=all" },
  { tag: "type=active", q: "?type=active" },
  { tag: "type=both", q: "?type=both" },
];

(async () => {
  const browser = await chromium.launch({
    headless: false, executablePath: EDGE,
    args: ["--disable-blink-features=AutomationControlled", "--start-maximized"],
  });
  const ctx = await browser.newContext({ ignoreHTTPSErrors: true, viewport: null });
  const page = await ctx.newPage();

  let loggedIn = false, csrf = null;
  page.on("request", (req) => {
    const h = req.headers();
    for (const k of Object.keys(h)) {
      if (/csrf|verification/i.test(k) && h[k] && h[k].length > 8) csrf = { name: k, value: h[k] };
    }
  });
  page.on("response", (res) => {
    if (/user_login_proof/.test(res.url()) && res.status() === 200 && !loggedIn) {
      loggedIn = true; log("=== 登录成功 ===");
    }
  });

  log("打开路由器…");
  await page.goto(BASE + "/html/index.html", { waitUntil: "domcontentloaded", timeout: 40000 });
  log("=== 请登录（约 40 秒后自动开始探测）===");

  const deadline = Date.now() + 10 * 60 * 1000;
  while (Date.now() < deadline && !loggedIn) await page.waitForTimeout(1200);

  if (!loggedIn) { log("!! 未登录，退出"); await page.waitForTimeout(30000); try { await browser.close(); } catch (e) { } return; }
  await page.waitForTimeout(4000);

  const results = [];
  for (const t of TARGETS) {
    const base = "/api/" + t;
    const row = { target: t, variants: [] };
    for (const v of VARIANTS) {
      const u = base + v.q;
      let r;
      try {
        r = await page.evaluate(async ({ u, name, value }) => {
          const hdr = { "Accept": "application/json, text/plain, */*", "X-Requested-With": "XMLHttpRequest" };
          if (name && value) hdr[name] = value;
          const ctl = new AbortController();
          const timer = setTimeout(() => ctl.abort(), 5000);
          try {
            const res = await fetch(u, { method: "GET", credentials: "include", headers: hdr, signal: ctl.signal });
            const text = await res.text();
            return { status: res.status, len: text.length, head: text.slice(0, 160) };
          } catch (e) { return { status: 0, err: String(e).slice(0, 80) }; }
          finally { clearTimeout(timer); }
        }, { u, name: csrf ? csrf.name : null, value: csrf ? csrf.value : null });
      } catch (e) { r = { status: -1, err: String(e).slice(0, 80) }; }
      row.variants.push({ tag: v.tag, status: r.status, len: r.len || 0, head: r.head || "" });
      await page.waitForTimeout(200);
    }
    const okv = row.variants.filter(x => x.status === 200).map(x => x.tag);
    log(`${t.padEnd(34)} ${row.variants.map(x => x.status).join("/")}  ${okv.length ? "OK→" + okv.join(",") : ""}`);
    if (okv.length) {
      // 存一份成功的
      const good = row.variants.find(x => x.status === 200);
      fs.writeFileSync(path.join(OUT, "api", t.replace(/[\/]/g, "_") + ".json"), good.head, "utf8");
    }
    results.push(row);
  }

  fs.writeFileSync(path.join(OUT, "reprobe.json"), JSON.stringify(results, null, 1), "utf8");
  log("完成，结果在 reprobe.json");
  await page.waitForTimeout(40 * 1000);
  try { await browser.close(); } catch (e) { }
})().catch((e) => { console.error("脚本出错:", e); process.exit(1); });
