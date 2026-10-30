/* 请求头矩阵实验 v5：确定 wlanfilterenhance 这类接口到底需要哪个请求头。
   对照 4 种组合，只发 GET。同时把 wlanfilterenhance 的完整返回存下来。 */
const { chromium } = require("playwright-core");
const fs = require("fs");
const path = require("path");

const OUT = path.join(__dirname, "..", "..", ".tmp-render", "fw-live");
const EDGE = process.env.HRC_EDGE || "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe";
const BASE = process.env.HRC_ROUTER || "http://192.168.3.1";
const stamp = () => new Date().toISOString().slice(11, 19);
const log = (...a) => console.log(stamp(), ...a);

/* 上次 404、这次 200 的，以及几个存疑的 */
const TARGETS = [
  "ntwk/wlanfilterenhance",
  "ntwk/urlfilter",
  "ntwk/timecontrol",
  "ntwk/multi_ssid",
  "ntwk/wlanwps",
  "app/qos",
  "ntwk/portforwarding",
  "ntwk/tunnel",
  "system/online_check",
  "ntwk/wlan_time_switch_list",
  "hilink/slavedevinfo",
  "device/l2topo",
  "ntwk/fwmacfilter",
];

(async () => {
  const browser = await chromium.launch({
    headless: false, executablePath: EDGE,
    args: ["--disable-blink-features=AutomationControlled", "--start-maximized"],
  });
  const ctx = await browser.newContext({ ignoreHTTPSErrors: true, viewport: null });
  const page = await ctx.newPage();

  let loggedIn = false;
  let csrf = null;
  page.on("request", (req) => {
    const h = req.headers();
    for (const k of Object.keys(h)) {
      if (/csrf|verification/i.test(k) && h[k] && h[k].length > 8) {
        if (!csrf || csrf.name !== k) log("学到 CSRF 头名:", k);
        csrf = { name: k, value: h[k] };
      }
    }
  });
  page.on("response", (res) => {
    if (/user_login_proof/.test(res.url()) && res.status() === 200 && !loggedIn) {
      loggedIn = true; log("=== 登录成功 ===");
    }
  });

  log("打开路由器…");
  await page.goto(BASE + "/html/index.html", { waitUntil: "domcontentloaded", timeout: 40000 });
  log("=== 请登录（最后一次，之后不用再登了）===");

  const deadline = Date.now() + 10 * 60 * 1000;
  while (Date.now() < deadline && !loggedIn) await page.waitForTimeout(1200);
  if (!loggedIn) { log("!! 未登录"); await page.waitForTimeout(30000); try { await browser.close(); } catch (e) { } return; }
  await page.waitForTimeout(5000);
  log("CSRF 头状态:", csrf ? csrf.name : "没学到");

  const COMBOS = [
    { tag: "裸GET", xrw: false, useCsrf: false },
    { tag: "带XRW", xrw: true, useCsrf: false },
    { tag: "带CSRF", xrw: false, useCsrf: true },
    { tag: "XRW+CSRF", xrw: true, useCsrf: true },
  ];

  const report = [];
  for (const t of TARGETS) {
    const row = { target: t, results: [] };
    let full = null;
    for (const c of COMBOS) {
      let r;
      try {
        r = await page.evaluate(async ({ u, xrw, cname, cval }) => {
          const hdr = { "Accept": "application/json, text/plain, */*" };
          if (xrw) hdr["X-Requested-With"] = "XMLHttpRequest";
          if (cname && cval) hdr[cname] = cval;
          const ctl = new AbortController();
          const timer = setTimeout(() => ctl.abort(), 6000);
          try {
            const res = await fetch(u, { method: "GET", credentials: "include", headers: hdr, signal: ctl.signal });
            const text = await res.text();
            return { status: res.status, len: text.length, text };
          } catch (e) { return { status: 0, err: String(e).slice(0, 80) }; }
          finally { clearTimeout(timer); }
        }, { u: "/api/" + t, xrw: c.xrw, cname: csrf ? csrf.name : null, cval: csrf ? csrf.value : null });
      } catch (e) { r = { status: -1, err: String(e).slice(0, 80) }; }
      row.results.push({ tag: c.tag, status: r.status, len: r.len || 0 });
      if (r.status === 200 && !full && r.text && r.text.length > 2) full = r.text;
      await page.waitForTimeout(180);
    }
    log(`${t.padEnd(32)} ${row.results.map(x => x.tag + "=" + x.status).join("  ")}`);
    if (full) {
      fs.writeFileSync(path.join(OUT, "api", t.replace(/\//g, "_") + ".json"), full, "utf8");
      row.saved = full.length;
    }
    report.push(row);
  }

  fs.writeFileSync(path.join(OUT, "header-matrix.json"), JSON.stringify(report, null, 1), "utf8");
  log("=== 完成 ===");
  await page.waitForTimeout(40 * 1000);
  try { await browser.close(); } catch (e) { }
})().catch((e) => { console.error("出错:", e); process.exit(1); });
