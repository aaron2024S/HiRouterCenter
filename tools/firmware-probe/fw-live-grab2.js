/* 真机取证 v2：即时落盘版。
   改进：
     1) 任何一个关键响应一到手就立刻写文件（v1 等最后统一写，浏览器一关全丢）
     2) 登录成功立刻落盘 HostInfo，然后自动跳到设备页触发固件自己请求 topology
     3) 全程不主动关浏览器，用户自己关
   只读，不改任何设置。 */
const { chromium } = require("playwright-core");
const fs = require("fs");
const path = require("path");

const OUT = path.join(__dirname, "..", "..", ".tmp-render", "fw-live");
fs.mkdirSync(OUT, { recursive: true });
const EDGE = process.env.HRC_EDGE || "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe";
const BASE = process.env.HRC_ROUTER || "http://192.168.3.1";

const stamp = () => new Date().toISOString().slice(11, 19);
const log = (...a) => console.log(stamp(), ...a);
const safe = (s) => s.replace(/[^A-Za-z0-9_.-]/g, "_").slice(0, 80);

let saved = 0;
function saveNow(tag, text) {
  try {
    const f = path.join(OUT, tag + ".json");
    fs.writeFileSync(f, text, "utf8");
    saved++;
    log(">>> 已落盘", tag + ".json", text.length + " 字符");
  } catch (e) { log("写文件失败", tag, String(e)); }
}

/* 哪些响应值得存 */
function tagOf(url) {
  const u = url.replace(/^https?:\/\/[^/]+/, "");
  if (/HostInfo/i.test(u)) return "hostinfo";
  if (/device\/topology/i.test(u)) return "topology";
  if (/wlanfilter/i.test(u)) return "wlanfilter";
  if (/hilink_status/i.test(u)) return "hilink_status";
  if (/device_count/i.test(u)) return "device_count";
  if (/system\/deviceinfo/i.test(u)) return "deviceinfo";
  if (/repeaterstate/i.test(u)) return "repeaterstate";
  return null;
}

(async () => {
  const browser = await chromium.launch({
    headless: false, executablePath: EDGE,
    args: ["--disable-blink-features=AutomationControlled", "--start-maximized"],
  });
  const ctx = await browser.newContext({ ignoreHTTPSErrors: true, viewport: null });
  const page = await ctx.newPage();

  let loggedIn = false;
  const allUrls = [];
  let csrf = null;

  page.on("request", (req) => {
    const u = req.url();
    if (u.indexOf("/api/") < 0) return;
    const h = req.headers();
    for (const k of Object.keys(h)) {
      if (/csrf|verification/i.test(k) && h[k] && h[k].length > 8) {
        if (!csrf || csrf.value !== h[k]) { csrf = { name: k, value: h[k] }; log("学到 CSRF 头:", k); }
      }
    }
  });

  page.on("response", async (res) => {
    const u = res.url();
    if (u.indexOf("/api/") < 0) return;
    const short = u.replace(/^https?:\/\/[^/]+/, "");
    allUrls.push(res.status() + " " + short);
    if (/user_login_proof/.test(short) && res.status() === 200) {
      if (!loggedIn) { loggedIn = true; log("=== 检测到登录成功 ==="); }
    }
    const tag = tagOf(u);
    if (!tag) return;
    try {
      const t = await res.text();
      if (t && t.length > 2) {
        saveNow(tag, t);
        if (tag === "hostinfo") log("  HostInfo 共", t.length, "字符");
      }
    } catch (e) { }
  });

  log("打开路由器页面…");
  await page.goto(BASE + "/html/index.html", { waitUntil: "domcontentloaded", timeout: 40000 });
  log("=== 请在浏览器里登录（登录后我会自动跳设备页，全程别关窗口）===");

  const deadline = Date.now() + 10 * 60 * 1000;
  while (Date.now() < deadline && !loggedIn) await page.waitForTimeout(1500);

  if (!loggedIn) { log("!! 没检测到登录，已抓到的仍会保留"); }
  else {
    await page.waitForTimeout(5000);          // 让首页把 HostInfo 发完
    log("跳到设备页触发拓扑请求…");
    for (const hash of ["#/devicecontrol", "#/home", "#/index"]) {
      try {
        await page.goto(BASE + "/html/index.html" + hash, { waitUntil: "domcontentloaded", timeout: 25000 });
        log("已打开", hash);
        await page.waitForTimeout(8000);
        if (fs.existsSync(path.join(OUT, "topology.json"))) { log("拿到 topology 了"); break; }
      } catch (e) { log("打开", hash, "失败:", String(e).slice(0, 80)); }
    }
  }

  /* 还没拿到 topology？主动请求（csrf 可能不需要 header，靠 cookie） */
  if (!fs.existsSync(path.join(OUT, "topology.json"))) {
    log("被动没抓到，改主动请求 /api/device/topology…");
    const r = await page.evaluate(async ({ name, value }) => {
      const out = {};
      const hdr = { "Content-Type": "application/json;charset=UTF-8" };
      if (name) hdr[name] = value;
      for (const [m, b] of [["POST", "{}"], ["GET", null]]) {
        try {
          const res = await fetch("/api/device/topology", { method: m, credentials: "include", headers: hdr, body: b });
          out[m] = { status: res.status, text: await res.text() };
        } catch (e) { out[m] = { error: String(e) }; }
      }
      return out;
    }, { name: csrf ? csrf.name : null, value: csrf ? csrf.value : null });

    for (const m of ["POST", "GET"]) {
      const d = r[m] || {};
      log("主动", m, d.status || d.error, d.text ? d.text.length + " 字符" : "");
      if (d.status === 200 && d.text && d.text.length > 2) {
        saveNow("topology", d.text);
        break;
      }
    }
    fs.writeFileSync(path.join(OUT, "topology_probe.txt"), JSON.stringify(r, null, 1), "utf8");
  }

  fs.writeFileSync(path.join(OUT, "urls.txt"), allUrls.join("\n"), "utf8");
  log("抓到的 api 请求:", allUrls.length, "条，落盘", saved, "个文件");
  log("浏览器保持打开，你看完自己关就行。全部文件在", OUT);

  await page.waitForTimeout(90 * 1000);   // 留 90 秒给人看，然后自己退出
  try { await browser.close(); } catch (e) { }
})().catch((e) => { console.error("脚本出错:", e); process.exit(1); });
