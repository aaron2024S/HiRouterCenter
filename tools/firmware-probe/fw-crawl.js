/* 真机全接口取证 v3：登录后把固件路由表里所有「只读」接口逐个 GET 一遍。
   原则：
     - 只发 GET，绝不发 POST（固件写操作全走 POST）
     - 串行 + 间隔 250ms，不给路由器压力
     - 每个响应到手立刻落盘，用户中途关窗口也不丢已抓的
     - 明确有副作用的接口（重启/升级/恢复/上传/改密/诊断/扫描…）整条跳过
   产出：.tmp-render/fw-live/api/<key>.json + crawl-index.json */
const { chromium } = require("playwright-core");
const fs = require("fs");
const path = require("path");

const OUT = path.join(__dirname, "..", "..", ".tmp-render", "fw-live");
const API_DIR = path.join(OUT, "api");
const LIST = path.join(__dirname, "fetch-list.json");
const EDGE = process.env.HRC_EDGE || "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe";
const BASE = process.env.HRC_ROUTER || "http://192.168.3.1";
fs.mkdirSync(API_DIR, { recursive: true });

const stamp = () => new Date().toISOString().slice(11, 19);
const log = (...a) => console.log(stamp(), ...a);

const list = JSON.parse(fs.readFileSync(LIST, "utf8"));

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
    const u = req.url();
    if (u.indexOf("/api/") < 0) return;
    const h = req.headers();
    for (const k of Object.keys(h)) {
      if (/csrf|verification/i.test(k) && h[k] && h[k].length > 8) {
        if (!csrf || csrf.name !== k) { csrf = { name: k, value: h[k] }; log("学到 CSRF 头:", k); }
        else csrf.value = h[k];
      }
    }
  });
  page.on("response", (res) => {
    if (res.url().indexOf("/api/") >= 0 && /user_login_proof/.test(res.url()) && res.status() === 200) {
      if (!loggedIn) { loggedIn = true; log("=== 检测到登录成功 ==="); }
    }
  });

  log("打开路由器页面…");
  await page.goto(BASE + "/html/index.html", { waitUntil: "domcontentloaded", timeout: 40000 });
  log("=== 请在浏览器里登录，登录后我自动开始抓全部接口（约 1~2 分钟），期间别关窗口 ===");

  const deadline = Date.now() + 10 * 60 * 1000;
  while (Date.now() < deadline && !loggedIn) await page.waitForTimeout(1200);

  if (!loggedIn) {
    log("!! 没检测到登录，退出");
    fs.writeFileSync(path.join(OUT, "crawl-index.json"),
      JSON.stringify({ ok: false, reason: "没登录" }, null, 1), "utf8");
    await page.waitForTimeout(60000);
    try { await browser.close(); } catch (e) { }
    return;
  }

  await page.waitForTimeout(4000);   // 首页自己的请求先发完

  /* 在页面上下文里跑：串行 GET 全部安全接口，逐条回传 */
  const index = [];
  for (const item of list.safe) {
    const url = "/api/" + item.path;
    let r;
    try {
      r = await page.evaluate(async ({ u, name, value }) => {
        const hdr = { "Accept": "application/json, text/plain, */*" };
        if (name && value) hdr[name] = value;
        const ctl = new AbortController();
        const timer = setTimeout(() => ctl.abort(), 6000);
        try {
          const res = await fetch(u, { method: "GET", credentials: "include", headers: hdr, signal: ctl.signal });
          const text = await res.text();
          return { status: res.status, len: text.length, text };
        } catch (e) {
          return { status: 0, len: 0, err: String(e).slice(0, 120) };
        } finally { clearTimeout(timer); }
      }, { u: url, name: csrf ? csrf.name : null, value: csrf ? csrf.value : null });
    } catch (e) {
      r = { status: -1, len: 0, err: String(e).slice(0, 120) };
    }

    const rec = { key: item.key, path: item.path, url, status: r.status, len: r.len || 0 };
    if (r.err) rec.err = r.err;
    if (r.text && r.text.length > 1) {
      fs.writeFileSync(path.join(API_DIR, item.key + ".json"), r.text, "utf8");
      rec.saved = true;
    }
    index.push(rec);
    log(`${String(r.status).padStart(3)} ${String(rec.len).padStart(7)}  ${item.key}  ${item.path}`);
    await page.waitForTimeout(250);
  }

  fs.writeFileSync(path.join(OUT, "crawl-index.json"), JSON.stringify({
    ok: true, at: new Date().toISOString(),
    total: list.safe.length,
    ok200: index.filter(x => x.status === 200).length,
    saved: index.filter(x => x.saved).length,
    skipped: list.skip,
    items: index,
  }, null, 1), "utf8");

  const ok = index.filter(x => x.status === 200).length;
  log(`=== 抓完：${ok}/${list.safe.length} 个返回 200，落盘 ${index.filter(x => x.saved).length} 个 ===`);
  log("文件在", API_DIR);

  await page.waitForTimeout(50 * 1000);
  try { await browser.close(); } catch (e) { }
})().catch((e) => { console.error("脚本出错:", e); process.exit(1); });
