# -*- coding: utf-8 -*-
"""HiRouterCenter 的单页前端（HTML + CSS + JS 全内联，零构建、零外部资源）。

由 .tmp-render/hrc/demo.html 的样式与图标集 + 生产版 body/JS 拼成，
页面本身不含任何模拟数据，所有内容都来自 /api/*。
修改时直接改这里（或改 .tmp-render/hrc 下的源文件重新生成）。
"""
from __future__ import annotations

PAGE = r'''<!doctype html>
<html lang="zh-CN" data-theme="dark">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>HiRouterCenter</title>
<style>/* ===== 设计令牌：iris（蓝紫）主题，深色为默认 ===== */
:root{
  --ink-950:#06070d; --ink-900:#0a0b14; --ink-875:#0c0e18; --ink-850:#0e101c;
  --ink-800:#111324; --ink-750:#15172b; --ink-700:#181a30; --ink-650:#1f2239;
  --line-1:#232741; --line-2:#1b1e33; --line-3:#2a2e4a; --line-4:#353a5c;
  --text-1:#e9eaf6; --text-2:#bfc2d8; --text-3:#989cb6; --text-4:#8b8fa9;
  --text-5:#616682; --text-6:#4f5370;
  --accent:#8b8cf8; --accent-deep:#4b4a9e; --accent-ink:#0a0a1c; --accent-soft:#1a1b33;
  --accent-text:#b3b4ff; --accent-hover:#a3a4ff;
  --accent-line:rgba(139,140,248,.5); --accent-ring:rgba(139,140,248,.1);
  --accent-row:rgba(139,140,248,.04); --soft-accent:rgba(139,140,248,.08);
  --line-accent-soft:rgba(139,140,248,.28);
  --run:#3ddc97; --run-text:#5ce8ab; --stop:#5d6280; --stop-text:#9498b3;
  --warn:#f2b263; --warn-text:#f8c583; --err:#f4737d; --err-text:#f79aa1;
  --chart-2:#5bc8f5;
  --soft-ok:rgba(61,220,151,.1); --soft-warn:rgba(242,178,99,.09); --soft-err:rgba(244,115,125,.08);
  --line-ok:rgba(61,220,151,.4); --line-warn:rgba(242,178,99,.35); --line-err:rgba(244,115,125,.35);
  --line-row:#1d2036; --line-hover:#454a72; --btn-bg:#171a2c; --hover:#1c1f36;
  --track:#2d3150; --thumb:#8b8fa9; --scrollbar:#252942; --scrollbar-hover:#363b5c;
  --shadow-pop:0 12px 30px rgba(2,3,10,.6); --shadow-modal:0 20px 60px rgba(2,3,10,.6);
  --font:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Helvetica Neue",Arial,
    "PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif;
  --mono:ui-monospace,SFMono-Regular,Menlo,Consolas,"Liberation Mono",
    "Microsoft YaHei","PingFang SC",monospace;
}
html[data-theme="light"]{
  --ink-950:#e9ebf4; --ink-900:#f2f4fa; --ink-875:#eef1f8; --ink-850:#fbfcff;
  --ink-800:#f1f3fa; --ink-750:#f5f7fc; --ink-700:#ffffff; --ink-650:#eceffa;
  --line-1:#e2e6f2; --line-2:#e6eaf4; --line-3:#d6dbeb; --line-4:#c6cce0;
  --text-1:#111428; --text-2:#343a55; --text-3:#4a5170; --text-4:#5d6480;
  --text-5:#7e8499; --text-6:#9ba1b5;
  --accent:#5b58d6; --accent-deep:#403eb0; --accent-ink:#fff; --accent-soft:#ecebff;
  --accent-text:#4f4cc9; --accent-hover:#4643bd;
  --accent-line:rgba(91,88,214,.45); --accent-ring:rgba(91,88,214,.14);
  --accent-row:rgba(91,88,214,.045); --soft-accent:rgba(91,88,214,.07);
  --line-accent-soft:rgba(91,88,214,.24);
  --run:#12a065; --run-text:#0d7d4f; --stop:#9aa0b8; --stop-text:#6b7189;
  --warn:#c47a13; --warn-text:#a1620c; --err:#d34350; --err-text:#c02f3d;
  --chart-2:#0d9bd4;
  --soft-ok:rgba(18,160,101,.09); --soft-warn:rgba(196,122,19,.1); --soft-err:rgba(211,67,80,.07);
  --line-ok:rgba(18,160,101,.32); --line-warn:rgba(196,122,19,.34); --line-err:rgba(211,67,80,.3);
  --line-row:#eaeef7; --line-hover:#aab2c9; --btn-bg:#fff; --hover:#f0f3fb;
  --track:#d8ddec; --thumb:#98a0b8; --scrollbar:#c9d0e2; --scrollbar-hover:#adb6cd;
  --shadow-pop:0 10px 26px rgba(22,28,58,.13);
  --shadow-modal:0 18px 50px rgba(22,28,58,.17);
  color-scheme:light;
}

/* ===== 基础 ===== */
*{box-sizing:border-box;scrollbar-width:thin;scrollbar-color:var(--scrollbar) transparent}
*::-webkit-scrollbar{width:9px;height:9px}
*::-webkit-scrollbar-track{background:transparent}
*::-webkit-scrollbar-thumb{background:var(--scrollbar);border-radius:999px;border:2px solid transparent;background-clip:content-box}
html,body{height:100%}
body{margin:0;background:var(--ink-950);color:var(--text-1);font-family:var(--font);
  font-size:13px;line-height:1.55;-webkit-font-smoothing:antialiased;
  -webkit-text-size-adjust:100%;text-size-adjust:100%}
input,select,textarea,button{font:inherit;color:inherit}
input::placeholder{color:var(--text-5)}
code,pre,.mono{font-family:var(--mono)}
:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.hide{display:none!important}
/* 自定义图标：细线 1.7 + 内部淡填充（duotone），和纯线性图标区分开 */
svg.i{width:15px;height:15px;flex:none;stroke:currentColor;fill:none;
  stroke-width:1.7;stroke-linecap:round;stroke-linejoin:round}
svg.i .f{fill:currentColor;fill-opacity:.18;stroke:none}
svg.i .ff{fill:currentColor;stroke:none}

/* ===== 关于页：作者与项目 ===== */
.authrow{display:flex;align-items:center;gap:11px;margin-bottom:13px}
.authrow .avatar{height:38px;width:38px;border-radius:11px;font-size:14px}
.authrow .t b{display:block;font-size:13.5px;font-weight:600}
.authrow .t span{font-size:11.5px;color:var(--text-5)}
.lnk{display:flex;align-items:center;gap:9px;border:1px solid var(--line-2);
  border-radius:10px;background:var(--ink-800);padding:9px 11px;color:var(--text-2);
  text-decoration:none;font-size:12.5px;transition:border-color .15s,background .15s}
.lnk + .lnk{margin-top:7px}
.lnk > span{white-space:nowrap;flex:none}
a.lnk:hover{border-color:var(--line-4);background:var(--ink-750)}
.lnk .u{margin-left:auto;font-family:var(--mono);font-size:11px;color:var(--text-5);
  overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.lnk .go{color:var(--text-5);margin-left:2px}
a.lnk:hover .go{color:var(--accent-text)}
.lnk.plain{cursor:default}

/* ===== 骨架 ===== */
.shell{display:flex;flex-direction:column;height:100vh;overflow:hidden;background:var(--ink-950)}
.topbar{display:flex;height:52px;flex:none;align-items:center;gap:10px;
  border-bottom:1px solid var(--line-2);background:var(--ink-850);padding:0 18px}
.logo{display:grid;width:27px;height:27px;flex:none;place-items:center;
  border-radius:9px;background:var(--accent);color:var(--accent-ink)}
.brand{flex:none;font-size:14px;font-weight:600;letter-spacing:.2px}
.ctx{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;
  font-size:12px;color:var(--text-4)}
.topright{margin-left:auto;display:flex;align-items:center;gap:8px}
#menuBtn{display:none}
.body{display:flex;min-height:0;flex:1}
.sidebar{z-index:40;display:flex;flex:none;flex-direction:column;width:176px;
  border-right:1px solid var(--line-2);background:var(--ink-875);padding:14px 10px}
.nav{display:flex;min-height:0;flex:1;flex-direction:column;gap:2px;overflow-y:auto}
.navg{padding:12px 10px 5px;font-size:11px;letter-spacing:.5px;color:var(--text-6)}
.ni{display:flex;width:100%;align-items:center;gap:9px;border:0;background:transparent;
  border-radius:9px;padding:8px 10px;text-align:left;font-size:13px;color:var(--text-3);
  cursor:pointer;transition:background .15s,color .15s}
.ni:hover{background:var(--ink-700);color:var(--text-1)}
.ni[aria-current="true"]{background:var(--accent-soft);color:var(--accent-text)}
.ni .cnt{margin-left:auto;flex:none;border-radius:6px;padding:0 6px;
  font-size:11px;line-height:18px;background:var(--ink-700);color:var(--text-5)}
.ni[aria-current="true"] .cnt{background:var(--accent-soft);color:var(--accent-text)}
.nifoot{margin-top:4px;flex:none;border-top:1px solid var(--line-2);padding-top:6px}
.main{min-height:0;flex:1;overflow:auto;background:var(--ink-900)}
.page{display:flex;flex-direction:column;gap:14px;padding:18px}

/* ===== 页头 / 卡片 ===== */
.phead{display:flex;flex-wrap:wrap;align-items:center;gap:10px}
.h1{font-size:15px;font-weight:600}
.sub{font-size:12px;color:var(--text-4)}
.phead-right{margin-left:auto;display:flex;flex-wrap:wrap;gap:8px}
.card{background:var(--ink-700);border:1px solid var(--line-1);border-radius:14px}
.card.accent{border-color:var(--line-accent-soft);background:var(--soft-accent)}
.ch{display:flex;align-items:center;gap:8px;border-bottom:1px solid var(--line-1);
  padding:12px 14px;font-weight:600}
.ch .i{color:var(--text-4)}
.ch .hint{margin-left:auto;font-size:11.5px;font-weight:400;color:var(--text-5)}
.cb{padding:14px}

/* ===== 路由器信息卡（首页顶部） ===== */
.rc-head{display:flex;align-items:center;gap:13px;padding:15px 16px}
.rc-mark{display:grid;width:46px;height:46px;flex:none;place-items:center;border-radius:13px;
  background:linear-gradient(150deg,var(--accent-soft),var(--ink-650));
  border:1px solid var(--line-accent-soft);color:var(--accent-text)}
.rc-mark svg{width:26px;height:26px;stroke:currentColor;fill:none;stroke-width:1.9;
  stroke-linecap:round;stroke-linejoin:round}
.rc-mark svg .f{fill:currentColor;stroke:none}
.rc-id{min-width:0;flex:1}
.rc-id .n{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;
  font-size:15px;font-weight:600;letter-spacing:.1px}
.rc-id .m{margin-top:2px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;
  font-size:11.5px;color:var(--text-5)}
.rc-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));
  border-top:1px solid var(--line-1)}
@media(min-width:820px){.rc-grid{grid-template-columns:repeat(4,minmax(0,1fr))}}
.kv{padding:11px 16px;border-right:1px solid var(--line-1);border-bottom:1px solid var(--line-1);
  min-width:0}
.kv:nth-child(2n){border-right:0}
@media(min-width:820px){
  .kv:nth-child(2n){border-right:1px solid var(--line-1)}
  .kv:nth-child(4n){border-right:0}
  .kv:nth-last-child(-n+4){border-bottom:0}
}
.kv:last-child,.kv:nth-last-child(2){border-bottom:0}
.kv .k{font-size:11px;color:var(--text-5);white-space:nowrap}
.kv .v{margin-top:3px;font-size:12.5px;font-weight:500;color:var(--text-1);
  overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.kv .v.mono{font-size:11.5px;font-weight:400;letter-spacing:.2px}
.kv .v .two{display:flex;flex-direction:column;gap:1px;white-space:normal}
.kv .v .two i{font-style:normal;font-family:var(--mono);font-size:11px;
  overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.kv .v .two em{font-style:normal;color:var(--text-5);margin-right:5px;font-family:var(--font)}
.cp{display:inline-flex;align-items:center;gap:5px;max-width:100%;border:0;background:transparent;
  padding:0;color:inherit;font:inherit;text-align:left;cursor:pointer}
.cp:hover{color:var(--accent-text)}
.cp .i{width:11px;height:11px;color:var(--text-6);flex:none}
.cp span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.cp.done{color:var(--run-text)}
.cp.done .i{color:var(--run)}

/* ===== 按钮 / 徽标 / 分段 ===== */
.btn{display:inline-flex;align-items:center;justify-content:center;gap:6px;
  border:1px solid var(--line-4);border-radius:9px;background:var(--btn-bg);
  color:var(--text-2);font-size:12.5px;padding:7px 13px;white-space:nowrap;
  cursor:pointer;transition:background .15s,border-color .15s,color .15s,opacity .15s}
.btn:hover:not(:disabled){border-color:var(--line-hover);color:var(--text-1)}
.btn:disabled{opacity:.45;cursor:not-allowed}
.btn-primary{background:var(--accent);border-color:var(--accent);color:var(--accent-ink);font-weight:600}
.btn-primary:hover:not(:disabled){background:var(--accent-hover);border-color:var(--accent-hover);color:var(--accent-ink)}
.btn-danger{background:var(--soft-err);border-color:var(--line-err);color:var(--err-text)}
.btn-sm{padding:5px 10px;font-size:12px}
.btn-ghost{background:transparent;border-color:transparent;color:var(--text-3)}
.btn-ghost:hover:not(:disabled){background:var(--hover);border-color:transparent;color:var(--text-1)}
.badge{display:inline-flex;align-items:center;gap:5px;border-radius:999px;
  padding:2px 9px;font-size:11px;line-height:1.6;white-space:nowrap}
.badge .dot{width:7px;height:7px;border-radius:999px}
.badge-run{background:var(--soft-ok);color:var(--run-text)}
.badge-run .dot{background:var(--run)}
.badge-stop{background:var(--line-2);color:var(--stop-text)}
.badge-stop .dot{background:var(--stop)}
.badge-warn{background:var(--soft-warn);color:var(--warn-text)}
.badge-warn .dot{background:var(--warn)}
.badge-accent{background:var(--accent-soft);color:var(--accent-text)}
.badge-err{background:var(--soft-err);color:var(--err-text)}
.badge-plain{background:var(--line-2);color:var(--text-4)}
.seg{display:inline-flex;gap:4px;border:1px solid var(--line-2);border-radius:10px;
  background:var(--ink-800);padding:3px}
.seg button{border:0;border-radius:7px;background:transparent;color:var(--text-3);
  font-size:12px;padding:5px 11px;cursor:pointer;white-space:nowrap;transition:all .15s}
.seg button:hover{color:var(--text-1)}
.seg button[data-on="true"]{background:var(--accent-soft);color:var(--accent-text)}
.chip{display:inline-flex;align-items:center;gap:5px;border:1px solid var(--line-3);
  border-radius:999px;background:transparent;color:var(--text-3);font-size:12px;
  padding:5px 11px;white-space:nowrap;cursor:pointer;transition:all .15s}
.chip:hover{border-color:var(--line-4);color:var(--text-1)}
.chip[data-on="true"]{background:var(--accent-soft);border-color:var(--accent-line);color:var(--accent-text)}
.chip .n{font-variant-numeric:tabular-nums;opacity:.75}
.sw{position:relative;display:inline-block;flex:none;width:34px;height:19px;
  border:0;border-radius:999px;background:var(--track);padding:0;cursor:pointer;
  transition:background .18s}
.sw::after{content:"";position:absolute;top:2px;left:2px;width:15px;height:15px;
  border-radius:50%;background:var(--thumb);transition:left .18s,background .18s}
.sw[data-on="true"]{background:var(--accent-deep)}
.sw[data-on="true"]::after{left:17px;background:var(--accent)}

/* ===== 表单 ===== */
.lbl{display:block;margin-bottom:5px;font-size:12px;color:var(--text-4)}
.inp,.sel,.area{width:100%;border:1px solid var(--line-3);border-radius:9px;
  background:var(--ink-800);color:var(--text-2);font-size:12.5px;padding:8px 11px;
  transition:border-color .15s,box-shadow .15s}
.inp:focus,.sel:focus,.area:focus{outline:none;border-color:var(--accent-line);
  box-shadow:0 0 0 3px var(--accent-ring)}
.sel{appearance:none;padding-right:30px;
  background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 24 24' fill='none' stroke='%23989cb6' stroke-width='2.5' stroke-linecap='round'%3E%3Cpath d='M6 9l6 6 6-6'/%3E%3C/svg%3E");
  background-repeat:no-repeat;background-position:right 10px center}
.wrap-inp{position:relative;min-width:180px;flex:1}
.wrap-inp .i{position:absolute;left:10px;top:50%;transform:translateY(-50%);
  color:var(--text-5);width:14px;height:14px;pointer-events:none}
.wrap-inp .inp{padding-left:32px}
.fieldrow{display:flex;align-items:flex-start;gap:12px;border-bottom:1px solid var(--line-row);
  padding:10px 0}
.fieldrow:last-child{border-bottom:0}
.fieldrow .t{min-width:200px;flex:1}
.fieldrow .t b{display:block;font-size:12.5px;font-weight:500}
.fieldrow .t span{font-size:11.5px;color:var(--text-5);line-height:1.5}
.fieldrow .ctl{flex:none}

/* ===== 进度条 ===== */
.bar{height:4px;border-radius:2px;background:var(--line-1);overflow:hidden}
.bar>i{display:block;height:100%;border-radius:2px;background:var(--accent);transition:width .3s}

/* ===== 表格 ===== */
.tblwrap{overflow-x:auto}
.tbl{width:100%;border-collapse:collapse}
.tbl th{position:sticky;top:0;z-index:1;border-bottom:1px solid var(--line-1);
  background:var(--ink-750);color:var(--text-5);font-size:11.5px;font-weight:500;
  text-align:left;padding:9px 14px;white-space:nowrap}
.tbl td{border-bottom:1px solid var(--line-row);padding:11px 14px;vertical-align:middle}
.tbl tr:last-child td{border-bottom:0}
.tbl tbody tr:hover{background:var(--accent-row)}
.tbl .mono{font-size:11.5px;color:var(--text-5)}
.tbl .acts{display:flex;gap:6px;justify-content:flex-end}
.tbl-fixed{table-layout:fixed;min-width:900px}
.tbl-fixed td{overflow:hidden}

/* ===== 设备卡片 ===== */
.filterrow{display:flex;flex-wrap:wrap;align-items:center;gap:10px}
.chips{display:flex;flex-wrap:wrap;gap:6px}
.devgrid{display:grid;grid-template-columns:1fr;gap:12px}
@media(min-width:760px){.devgrid{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(min-width:900px){.devgrid{grid-template-columns:repeat(3,minmax(0,1fr))}}
@media(min-width:1180px){.devgrid{grid-template-columns:repeat(5,minmax(0,1fr))}}
.dev{display:flex;flex-direction:column;gap:10px;border:1px solid var(--line-1);
  border-radius:14px;background:var(--ink-700);padding:12px;transition:border-color .15s}
.dev:hover{border-color:var(--line-4)}
.dev.off{opacity:.94}
.dev.black{border-color:var(--line-warn)}
.dev-head{display:flex;align-items:flex-start;gap:10px}
.avatar{display:grid;height:34px;width:34px;flex:none;place-items:center;border-radius:10px;
  border:0;padding:0;background:var(--line-2);color:var(--accent-text);
  font-size:13px;font-weight:600;transition:background .15s,box-shadow .15s}
.avatar svg.i{width:18px;height:18px;stroke-width:1.6}
.dev-head .avatar{cursor:pointer}
.dev-head .avatar:hover{background:var(--line-3);box-shadow:0 0 0 3px var(--soft-accent)}
.dev.off .avatar{color:var(--text-4)}

/* 设备类型选择浮层 */
.tpick-mask{position:fixed;inset:0;z-index:60;background:rgba(3,4,10,.62);
  display:grid;place-items:center;padding:16px}
html[data-theme="light"] .tpick-mask{background:rgba(30,34,56,.34)}
.tpick{width:min(440px,100%);max-height:min(580px,88vh);overflow:auto;
  border:1px solid var(--line-3);border-radius:16px;background:var(--ink-700);
  box-shadow:var(--shadow-modal)}
.tpick .th{display:flex;align-items:center;gap:8px;padding:13px 15px;
  border-bottom:1px solid var(--line-1);font-size:13px;font-weight:600}
.tpick .th .btn{margin-left:auto}
.tpick .tn{padding:10px 15px 0;font-size:11.5px;color:var(--text-5);
  overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.tgrid{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:6px;padding:11px 12px 13px}
.tcell{display:flex;flex-direction:column;align-items:center;gap:6px;border:1px solid transparent;
  border-radius:11px;background:var(--ink-800);padding:10px 4px 8px;cursor:pointer;
  color:var(--text-3);font-size:11px;line-height:1.25;text-align:center;
  transition:border-color .14s,color .14s,background .14s}
.tcell:hover{border-color:var(--line-4);color:var(--text-2)}
.tcell[data-on="true"]{border-color:var(--accent);background:var(--soft-accent);color:var(--accent-text)}
.tcell svg.i{width:19px;height:19px}
.tcell span{max-width:100%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}

/* ===== 路由器快捷操作 ===== */
.rc-acts{display:flex;flex-wrap:wrap;align-items:center;gap:8px;
  border-top:1px solid var(--line-1);padding:11px 16px}
.rc-acts-t{margin-right:2px;font-size:11px;color:var(--text-5);white-space:nowrap}
.rc-acts .btn b{font-weight:600;color:var(--accent-text)}
.qdlg{width:min(430px,100%);border:1px solid var(--line-3);border-radius:16px;
  background:var(--ink-700);box-shadow:var(--shadow-modal);display:flex;flex-direction:column}
.qdlg .th{display:flex;align-items:center;gap:8px;padding:13px 15px;
  border-bottom:1px solid var(--line-1);font-size:13px;font-weight:600}
.qdlg .th .btn{margin-left:auto}
.qbody{padding:14px 15px}
.qbody p{margin:0;font-size:12.5px;line-height:1.7;color:var(--text-3)}
.opts{display:flex;flex-direction:column;gap:7px;margin-top:12px}
.opt{display:flex;align-items:center;gap:10px;border:1px solid var(--line-2);border-radius:10px;
  background:var(--ink-800);padding:10px 12px;cursor:pointer;text-align:left;
  transition:border-color .14s,background .14s}
.opt:hover{border-color:var(--line-4)}
.opt[data-on="true"]{border-color:var(--accent);background:var(--soft-accent)}
.opt .rd{width:14px;height:14px;flex:none;border-radius:99px;border:1.6px solid var(--line-4)}
.opt[data-on="true"] .rd{border-color:var(--accent);box-shadow:inset 0 0 0 3px var(--accent)}
.opt .ot b{display:block;font-size:12.5px;font-weight:500}
.opt .ot span{font-size:11px;color:var(--text-5)}
.opt[data-on="true"] .ot b{color:var(--accent-text)}

/* 渠道编辑弹窗 */
.chanrow{display:flex;flex-wrap:wrap;align-items:center;gap:10px;
  border-bottom:1px solid var(--line-row);padding:12px 14px}
.chanrow:last-child{border-bottom:0}
.cinfo{min-width:170px;flex:1}
.cinfo .cn{font-size:12.5px;font-weight:500}
.cinfo .cs{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;
  font-size:11px;color:var(--text-5)}
.cacts{display:flex;gap:6px}
.epick{width:min(540px,100%);max-height:min(92vh,780px);display:flex;flex-direction:column;
  border:1px solid var(--line-3);border-radius:16px;background:var(--ink-700);
  box-shadow:var(--shadow-modal)}
.epick .th{display:flex;align-items:center;gap:8px;padding:13px 15px;flex:none;
  border-bottom:1px solid var(--line-1);font-size:13px;font-weight:600}
.epick .th .btn{margin-left:auto}
.ebody{display:flex;flex-direction:column;gap:12px;padding:14px 15px;overflow:auto}
.egrid2{display:grid;grid-template-columns:1fr 1fr;gap:10px}
.efld label{display:block;margin-bottom:5px;font-size:11.5px;color:var(--text-4)}
.efld label em{margin-left:3px;font-style:normal;color:var(--err-text)}
.efld .hp{margin-top:5px;font-size:11px;line-height:1.55;color:var(--text-5)}
.efld .miss{border-color:var(--err)!important;box-shadow:0 0 0 3px var(--soft-err)}
.epick .area{min-height:62px;resize:vertical;font-size:11.5px;line-height:1.6}
.efoot{display:flex;flex:none;justify-content:flex-end;gap:8px;padding:11px 15px;
  border-top:1px solid var(--line-1)}
.epick .desc{padding:9px 11px;border-radius:9px;background:var(--ink-800);
  font-size:11.5px;line-height:1.6;color:var(--text-4)}
.eon{display:flex;align-items:center;gap:9px;font-size:12.5px;color:var(--text-2);cursor:pointer}
.dev-id{min-width:0;flex:1}
.dev-id .n{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;
  font-size:13px;font-weight:600}
.dev-id .m{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;
  font-family:var(--mono);font-size:11px;color:var(--text-5);letter-spacing:.3px}
.dev-tags{display:flex;flex-wrap:wrap;gap:5px}
.dev-v6{display:flex;flex-direction:column;gap:4px}
.v6{display:flex;align-items:center;gap:6px;width:100%;border:1px solid var(--line-2);
  border-radius:8px;background:var(--ink-800);padding:5px 8px;cursor:pointer;
  text-align:left;font-family:var(--mono);font-size:11.5px;color:var(--text-3);
  transition:border-color .15s,color .15s,background .15s}
.v6:hover{border-color:var(--accent-line);color:var(--accent-text)}
.v6 .i{width:12px;height:12px;color:var(--text-6)}
.v6.copied{border-color:var(--line-ok);color:var(--run-text)}
.v6.copied .i{color:var(--run)}
.v6 span{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.v6 .first{color:var(--text-2)}
/* 卡片底部：只读的放行状态 + 唤醒 */
.dev-foot{display:flex;align-items:center;gap:8px;margin-top:auto;
  border-top:1px solid var(--line-2);padding-top:10px}
.dev-foot .fw{display:inline-flex;align-items:center;gap:5px;min-width:0;
  font-size:11.5px;color:var(--text-5)}
.dev-foot .fw .i{width:12px;height:12px;flex:none;color:var(--text-6)}
.dev-foot .fw b{font-weight:400;color:var(--text-3);font-family:var(--mono);font-size:11px;
  overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.dev-foot .fw.on{color:var(--run-text)}
.dev-foot .fw.on .i{color:var(--run)}
.dev-foot .btn{margin-left:auto;flex:none}

/* ===== 概览条 ===== */
.strip{display:grid;grid-template-columns:1fr;gap:16px}
@media(min-width:900px){.strip{grid-template-columns:1.1fr 1.1fr 1.3fr}}
.strip .col{display:flex;flex-direction:column;gap:7px}
.strip .row{display:flex;justify-content:space-between;font-size:11.5px;color:var(--text-4)}
.strip .row b{color:var(--text-2);font-weight:500;font-variant-numeric:tabular-nums;
  white-space:nowrap}
.swline{display:flex;align-items:center;gap:11px}
.swline .txt{min-width:0}
.swline .txt b{display:block;font-size:12.5px;font-weight:500}
.swline .txt span{font-size:11px;color:var(--text-5)}

/* 防火墙总开关条 */
.fwbar{display:flex;flex-wrap:wrap;align-items:center;gap:12px;padding:14px 16px}
.fwbar .ico{display:grid;width:36px;height:36px;flex:none;place-items:center;border-radius:11px;
  background:var(--accent-soft);color:var(--accent-text)}
.fwbar .txt{min-width:0;flex:1}
.fwbar .txt b{display:block;font-size:13px;font-weight:600}
.fwbar .txt span{font-size:11.5px;color:var(--text-5)}

/* ===== 触屏 / 窄屏（< 768）：侧栏改抽屉、点按目标抬高 ===== */
@media(max-width:767px){
  .sidebar{position:fixed;inset:0 auto 0 0;width:184px;z-index:40;
    transform:translateX(-100%);transition:transform .2s}
  .shell.navopen .sidebar{transform:none;box-shadow:var(--shadow-pop)}
  .scrim{position:fixed;inset:0;z-index:30;background:rgba(0,0,0,.55)}
  .topbar{gap:8px;padding:0 12px}
  .topbar #menuBtn{display:grid}
  .brand{font-size:13px}
  .ctx,.tlabel{display:none}
  .page{padding:12px;gap:11px}
  .phead-right{margin-left:auto;width:auto}
  .phead-right .btn{flex:0 1 auto}
  /* 手机上：标题和按钮同一行，副标题整宽落到第二行（否则长副标题会和标题挤成一坨） */
  .phead .h1{order:1}
  .phead-right{order:2}
  .phead .sub{order:3;flex:1 1 100%}
  .rc-head{padding:13px}
  .rc-mark{width:40px;height:40px;border-radius:11px}
  .rc-id .n{font-size:13.5px}
  .kv{padding:9px 13px}
  .strip{gap:13px}
  .swline{border-left:0;border-top:1px solid var(--line-1);padding-left:0;padding-top:13px}
  .fieldrow{flex-wrap:wrap;gap:8px}
  .fieldrow .t{min-width:100%}
  .fieldrow .ctl{width:100%!important}
  .fieldrow .ctl .inp,.fieldrow .ctl .sel{width:100%!important}
  .lnk .u{display:none}
  .lnk .go{margin-left:auto}
  .tgrid{grid-template-columns:repeat(4,minmax(0,1fr));gap:5px;padding:10px}
  .tcell{padding:9px 3px 7px;font-size:10.5px}
  #devType{width:auto!important;max-width:none!important;flex:1 1 132px;min-width:0}
  .filterrow .wrap-inp{max-width:none!important;margin-left:0!important;
    flex:1 1 132px;min-width:0}
  .seg{flex:none;max-width:100%;overflow-x:auto}
  .seg button{padding:8px 13px}
  .ch,.phead{flex-wrap:wrap;row-gap:8px}
  .btn{min-height:36px;padding:8px 14px}
  .btn-sm{min-height:34px;padding:7px 12px}
  .chip{min-height:34px;padding:7px 13px}
  .sw{width:46px;height:30px}
  .sw::after{width:24px;height:24px;top:3px;left:3px}
  .sw[data-on="true"]::after{left:19px}
  .inp,.sel{min-height:38px}
  .wrap-inp{max-width:none!important}
}

/* ===== 空态 / 提示条 ===== */
.banner{display:flex;align-items:center;gap:11px;border-radius:14px;padding:12px 15px;font-size:13px}
.banner-info{background:var(--soft-accent);border:1px solid var(--line-accent-soft);color:var(--accent-text)}
.banner-info .i{color:var(--accent)}
.banner-warn{background:var(--soft-warn);border:1px solid var(--line-warn);color:var(--warn-text)}
.dash{color:var(--text-6)}

/* ===== toast ===== */
.toasts{position:fixed;right:16px;bottom:16px;z-index:80;display:flex;
  flex-direction:column;gap:8px;max-width:calc(100vw - 32px)}
.toast{display:flex;align-items:flex-start;gap:9px;min-width:240px;max-width:360px;
  border:1px solid var(--line-3);border-radius:12px;background:var(--ink-750);
  box-shadow:var(--shadow-pop);padding:10px 12px;font-size:12.5px}
.toast .i{margin-top:1px;width:14px;height:14px;color:var(--run-text)}
.toast b{display:block;font-weight:600}
.toast span{font-size:11.5px;color:var(--text-5)}
/* ===== 登录门 / 补充组件（生产版新增，原型里没有） ===== */
.gate{position:fixed;inset:0;z-index:80;display:flex;align-items:center;
  justify-content:center;background:var(--ink-950);padding:20px}
.gatebox{display:flex;flex-direction:column;gap:10px;width:100%;max-width:330px;
  border:1px solid var(--line-2);border-radius:16px;background:var(--ink-850);
  padding:22px;box-shadow:var(--shadow-modal)}
.lgmark{display:grid;place-items:center;width:44px;height:44px;border-radius:13px;
  margin-bottom:2px;background:var(--accent);color:var(--accent-ink)}
.gatebox b{font-size:16px}
.gsub{margin-bottom:6px;font-size:12px;color:var(--text-4)}
.gerr{min-height:16px;font-size:12px;color:var(--err-text)}
.gatebox .efld{display:flex;flex-direction:column}
.gatebox .efld > span{margin-bottom:5px;font-size:11.5px;color:var(--text-4)}

/* 星期多选 / 唤醒设备多选 */
.wdays{display:flex;gap:6px}
.wday{width:34px;height:32px;border:1px solid var(--line-3);border-radius:8px;
  background:var(--btn-bg);font-size:12px;color:var(--text-3);cursor:pointer}
.wday[data-on="true"]{border-color:var(--accent-line);background:var(--accent-soft);
  color:var(--accent-text);font-weight:600}
.devpick{display:flex;flex-wrap:wrap;gap:6px;max-height:190px;overflow:auto;
  border:1px solid var(--line-2);border-radius:10px;padding:8px;background:var(--ink-800)}
.devchip{display:flex;flex-direction:column;align-items:flex-start;gap:1px;
  border:1px solid var(--line-3);border-radius:8px;background:var(--btn-bg);
  padding:5px 9px;font-size:12px;color:var(--text-2);text-align:left;cursor:pointer}
.devchip .mc{font-family:var(--mono);font-size:10px;color:var(--text-5)}
.devchip[data-off="true"]{opacity:.62}
.devchip[data-on="true"]{border-color:var(--accent-line);background:var(--accent-soft);
  color:var(--accent-text)}
.devchip[data-on="true"] .mc{color:var(--accent-text);opacity:.8}
.efld > span{margin-bottom:5px;font-size:11.5px;color:var(--text-4)}

/* 收起侧栏（桌面端） */
.shell.collapsed .sidebar{width:62px;padding-left:8px;padding-right:8px}
.shell.collapsed .sidebar .ni span:not(.cnt){display:none}
.shell.collapsed .sidebar .ni{justify-content:center;padding:9px 0}
.shell.collapsed .sidebar .ni .cnt{display:none}
.shell.collapsed .sidebar .navg{display:none}
.shell.collapsed #btnCollapse svg{transform:rotate(180deg)}

/* 登录门「保持登录（7 天）」 */
.ckrow{display:flex;align-items:center;gap:8px;font-size:12.5px;
  color:var(--text-3);cursor:pointer;user-select:none}
.ckrow input{width:15px;height:15px;margin:0;accent-color:var(--accent);cursor:pointer}
.ckrow:hover{color:var(--text-2)}
/* 关于页「维护」 */
.maint-row{display:flex;align-items:center;gap:10px;flex-wrap:wrap}

/* 设备卡：IPv4 行 + 离线设备的最后在线时间 */
.dev-meta{display:flex;flex-direction:column;gap:4px}
.laston{display:flex;align-items:center;gap:5px;font-size:11.5px;color:var(--text-5)}
.laston .i{width:12px;height:12px;opacity:.85}
/* 手机端筛选行：五个标签不再折成三行，横向滑动即可，避免「儿童上网」独占一行 */
@media(max-width:640px){
  .filterrow .chips{flex-wrap:nowrap;overflow-x:auto;scrollbar-width:none;flex:1 1 auto;min-width:0}
  .filterrow .chips::-webkit-scrollbar{display:none}
  .filterrow .chips .chip{flex:0 0 auto}
  .filterrow .sel{flex:0 0 auto;max-width:150px!important}
}
</style>
</head>
<body>
<svg width="0" height="0" style="position:absolute" aria-hidden="true"><defs>
<!-- 品牌 mark：路由器俯视 + 三根天线 + 指示灯 -->
<symbol id="i-mark" viewBox="0 0 32 32">
  <path class="f" d="M8 10h16a4 4 0 0 1 4 4v5a4 4 0 0 1-4 4H8a4 4 0 0 1-4-4v-5a4 4 0 0 1 4-4Z"/>
  <path d="M9 10V6.6M16 10V5.2M23 10V6.6" fill="none" stroke="currentColor"
    stroke-width="2.4" stroke-linecap="round"/>
  <circle cx="10" cy="16.5" r="1.7" fill="currentColor" stroke="none"/>
  <circle cx="16" cy="16.5" r="1.7" fill="currentColor" stroke="none" opacity=".62"/>
  <circle cx="22" cy="16.5" r="1.7" fill="currentColor" stroke="none" opacity=".3"/>
</symbol>

<!-- 侧栏图标：duotone（细线 + 淡填充） -->
<symbol id="i-devices" viewBox="0 0 24 24">
  <rect x="2.6" y="3.6" width="18.8" height="13.2" rx="2.6"/>
  <path class="f" d="M5.8 6.8h5.1v4H5.8zM13.1 6.8h5.1v4h-5.1zM5.8 12.3h12.4v1.9H5.8z"/>
  <path d="M8.6 20.4h6.8M12 16.8v3.6"/>
</symbol>
<symbol id="i-fw6" viewBox="0 0 24 24">
  <path d="M12 2.6 20 5.4v6.2c0 4.9-3.4 7.6-8 9.8-4.6-2.2-8-4.9-8-9.8V5.4l8-2.8Z"/>
  <path class="f" d="M12 7.4c2.5 0 4 1.6 4 3.6s-1.6 3.3-4 3.3-4-1.4-4-3.3 1.5-3.6 4-3.6Z" opacity=".5"/>
  <path d="M8.4 12.6h7.2M9.6 15.6h4.8" opacity=".8"/>
</symbol>
<symbol id="i-cal" viewBox="0 0 24 24">
  <rect x="3.2" y="5.2" width="17.6" height="15.4" rx="2.6"/>
  <path class="f" d="M6.4 8.6h11.2v3.1H6.4z"/>
  <path d="M8 2.8v3.2M16 2.8v3.2M3.2 10.4h17.6"/>
  <circle cx="15.4" cy="16" r="2.1"/>
</symbol>
<symbol id="i-bell" viewBox="0 0 24 24">
  <path d="M18 15.4c-.9-1-1.4-2.6-1.4-4.5a4.6 4.6 0 0 0-9.2 0c0 1.9-.5 3.5-1.4 4.5h12Z"/>
  <path class="f" d="M8.6 11.3a3.4 3.4 0 0 1 6.8 0c0 1.5.3 2.6.7 3.4H7.9c.4-.8.7-1.9.7-3.4Z"/>
  <path d="M10.2 18.4a2 2 0 0 0 3.6 0M18 6.2 19.8 4.4M6 6.2 4.2 4.4"/>
</symbol>
<symbol id="i-knob" viewBox="0 0 24 24">
  <path d="M4 6.6h16M4 17.4h16"/>
  <circle cx="9.4" cy="6.6" r="2.5" class="f"/>
  <circle cx="9.4" cy="6.6" r="2.5"/>
  <circle cx="15" cy="17.4" r="2.5" class="f"/>
  <circle cx="15" cy="17.4" r="2.5"/>
</symbol>
<symbol id="i-info" viewBox="0 0 24 24">
  <circle cx="12" cy="12" r="9.2"/>
  <path class="f" d="M12 10.6h0v6.2a1 1 0 0 0 2 0v-6.2Z"/>
  <circle cx="12" cy="7.7" r="1.2" stroke="none" class="f"/>
</symbol>
<symbol id="i-refresh" viewBox="0 0 24 24">
  <path d="M20.4 11.2a8.4 8.4 0 0 0-14.5-4.6L3.6 8.8"/>
  <path class="f" d="M3 4.4h5.6V10Z" opacity=".7"/>
  <path d="M3.6 12.8a8.4 8.4 0 0 0 14.5 4.6l2.3-2.2"/>
  <path class="f" d="M21 19.6h-5.6V14Z" opacity=".7"/>
</symbol>
<symbol id="i-plus" viewBox="0 0 24 24"><path d="M12 5.2v13.6M5.2 12h13.6"/></symbol>
<symbol id="i-search" viewBox="0 0 24 24">
  <circle cx="10.8" cy="10.8" r="7.2"/><path class="f" d="M10.8 5.6a5.2 5.2 0 0 1 0 10.4Z" opacity=".5"/>
  <path d="m16.2 16.2 4.4 4.4"/>
</symbol>
<symbol id="i-x" viewBox="0 0 24 24"><path d="M17.6 6.4 6.4 17.6M6.4 6.4l11.2 11.2"/></symbol>
<symbol id="i-chevleft" viewBox="0 0 24 24"><path d="m13.6 17.2-5.2-5.2 5.2-5.2"/></symbol>
<symbol id="i-power" viewBox="0 0 24 24">
  <path d="M12 3.4v7.8"/>
  <path d="M17.6 6.6a7.8 7.8 0 1 1-11.2 0"/>
</symbol>
<symbol id="i-copy" viewBox="0 0 24 24">
  <rect x="8.6" y="8.6" width="11.8" height="11.8" rx="2.4"/>
  <path class="f" d="M5.6 15.2h-.4A1.8 1.8 0 0 1 3.4 13.4V5.2a1.8 1.8 0 0 1 1.8-1.8h8.2a1.8 1.8 0 0 1 1.8 1.8v.4" opacity=".55"/>
  <path d="M5.6 15.2h-.4A1.8 1.8 0 0 1 3.4 13.4V5.2a1.8 1.8 0 0 1 1.8-1.8h8.2a1.8 1.8 0 0 1 1.8 1.8v.4"/>
</symbol>
<symbol id="i-check" viewBox="0 0 24 24"><path d="M19.4 6.6 9.4 17 4.6 12.2"/></symbol>
<symbol id="i-logout" viewBox="0 0 24 24">
  <path d="M9.4 20.4H5.6a2 2 0 0 1-2-2V5.6a2 2 0 0 1 2-2h3.8"/>
  <path d="M15.6 16.4 20 12l-4.4-4.4M20 12H9.2"/>
</symbol>
<symbol id="i-moon" viewBox="0 0 24 24">
  <path d="M20.4 14.6A8.6 8.6 0 0 1 9.4 3.6a8.6 8.6 0 1 0 11 11Z"/>
  <path class="f" d="M13.2 6.8a5 5 0 0 0 4 6 5 5 0 0 1-4-6Z" opacity=".6"/>
</symbol>
<symbol id="i-sun" viewBox="0 0 24 24">
  <circle cx="12" cy="12" r="4" class="f"/><circle cx="12" cy="12" r="4"/>
  <path d="M12 2.8v2M12 19.2v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2.8 12h2M19.2 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>
</symbol>
<symbol id="i-trash" viewBox="0 0 24 24">
  <path d="M3.6 6.4h16.8M9 6.4V4.6a1.6 1.6 0 0 1 1.6-1.6h2.8A1.6 1.6 0 0 1 15 4.6v1.8"/>
  <path d="M18.4 6.4v13.2a1.8 1.8 0 0 1-1.8 1.8H7.4a1.8 1.8 0 0 1-1.8-1.8V6.4"/>
  <path d="M10.2 10.6v6M13.8 10.6v6"/>
</symbol>
<symbol id="i-send" viewBox="0 0 24 24">
  <path d="M20.6 3.4 3.8 9.6a.6.6 0 0 0 0 1.1l7 2.5 2.5 7a.6.6 0 0 0 1.1 0l6.2-16.8Z"/>
  <path class="f" d="M11 13 20.6 3.4 10.2 12.2Z" opacity=".5"/>
</symbol>
<symbol id="i-alert" viewBox="0 0 24 24">
  <path d="M12 3.4 21.4 20H2.6Z"/>
  <path d="M12 9.4v4.4M12 16.8h.01"/>
</symbol>
<symbol id="i-history" viewBox="0 0 24 24">
  <path d="M3.6 12a8.4 8.4 0 1 0 2.6-6.1"/>
  <path class="f" d="M3.4 3.6h5v5Z" opacity=".7"/>
  <path d="M3.4 3.6v5h5"/>
  <path d="M12 7.8V12l3.2 1.9"/>
</symbol>
<symbol id="i-ban" viewBox="0 0 24 24">
  <circle cx="12" cy="12" r="8.6"/>
  <path d="m5.9 5.9 12.2 12.2"/>
</symbol>
<symbol id="i-clock" viewBox="0 0 24 24">
  <circle cx="12" cy="12" r="8.8"/>
  <path class="f" d="M12 6.4a5.6 5.6 0 0 1 0 11.2Z" opacity=".45"/>
  <path d="M12 7.2V12l3.4 2"/>
</symbol>
<symbol id="i-wifi" viewBox="0 0 24 24">
  <path d="M2.6 8.4a14.6 14.6 0 0 1 18.8 0" opacity=".45"/>
  <path d="M5.6 12.2a10.2 10.2 0 0 1 12.8 0"/>
  <path d="M8.6 15.9a5.8 5.8 0 0 1 6.8 0"/>
  <circle cx="12" cy="19.2" r="1.3" class="f"/>
  <circle cx="12" cy="19.2" r="1.3"/>
</symbol>
<symbol id="i-menu" viewBox="0 0 24 24"><path d="M4 7h16M4 12h16M4 17h10"/></symbol>
<symbol id="i-edit" viewBox="0 0 24 24">
  <path d="M11.4 5.6H5.6a2 2 0 0 0-2 2v10.8a2 2 0 0 0 2 2h10.8a2 2 0 0 0 2-2v-5.8"/>
  <path d="M17.4 3.6a2 2 0 0 1 2.9 2.9l-8.3 8.3-3.6.8.8-3.6 8.2-8.4Z"/>
</symbol>
<symbol id="i-zap" viewBox="0 0 24 24">
  <path d="M13.4 2.8 4.6 14h6.2l-.4 7.2 8.8-11.2h-6.2Z"/>
  <path class="f" d="M13.4 2.8 4.6 14h6.2Z" opacity=".55"/>
</symbol>
<symbol id="i-link" viewBox="0 0 24 24">
  <path d="M9.4 14.6 14.6 9.4"/>
  <path d="M11.2 6.4 13 4.6a4.2 4.2 0 0 1 5.9 5.9l-1.8 1.8"/>
  <path d="M12.8 17.6 11 19.4a4.2 4.2 0 0 1-5.9-5.9L6.9 11.7"/>
</symbol>
<symbol id="i-github" viewBox="0 0 24 24">
  <path class="ff" d="M12 2.2a9.9 9.9 0 0 0-3.13 19.3c.5.09.68-.21.68-.48v-1.83c-2.77.6-3.36-1.22-3.36-1.22-.45-1.15-1.11-1.46-1.11-1.46-.9-.62.07-.61.07-.61 1 .07 1.53 1.03 1.53 1.03.9 1.53 2.35 1.09 2.92.83.09-.65.35-1.09.63-1.35-2.22-.25-4.55-1.11-4.55-4.94 0-1.09.39-1.98 1.03-2.68-.1-.25-.45-1.27.1-2.64 0 0 .84-.27 2.75 1.02a9.4 9.4 0 0 1 5 0c1.91-1.29 2.75-1.02 2.75-1.02.55 1.37.2 2.39.1 2.64.64.7 1.03 1.59 1.03 2.68 0 3.84-2.34 4.69-4.57 4.93.36.31.68.92.68 1.85v2.74c0 .27.18.58.69.48A9.9 9.9 0 0 0 12 2.2Z"/>
</symbol>
<symbol id="i-issue" viewBox="0 0 24 24">
  <circle cx="12" cy="12" r="9.2"/>
  <path class="f" d="M12 7.6a4.4 4.4 0 0 1 0 8.8Z" opacity=".55"/>
  <circle cx="12" cy="12" r="1.6" class="ff"/>
</symbol>
<symbol id="i-tag" viewBox="0 0 24 24">
  <path d="M20.4 12.9 13 20.3a1.6 1.6 0 0 1-2.3 0l-7-7V3.4h9.6l6.9 6.9a1.8 1.8 0 0 1 .2 2.6Z"/>
  <circle cx="8.1" cy="8.1" r="1.6"/>
</symbol>
<symbol id="i-out" viewBox="0 0 24 24">
  <path d="M13.6 4.6h5.8v5.8"/>
  <path d="M19.4 4.6 11.6 12.4"/>
  <path d="M18.2 14.4v4a1.8 1.8 0 0 1-1.8 1.8H5.6a1.8 1.8 0 0 1-1.8-1.8V7.6a1.8 1.8 0 0 1 1.8-1.8h4"/>
</symbol>

<!-- ========== 设备类型图标（25 种，同一套 duotone 语言） ========== -->
<symbol id="t-nas" viewBox="0 0 24 24">
  <rect x="3.4" y="4.2" width="17.2" height="15.6" rx="2.4"/>
  <path d="M3.4 9.6h17.2M3.4 14.4h17.2"/>
  <circle cx="7" cy="6.9" r=".95" class="f"/>
  <circle cx="7" cy="12" r=".95" class="f"/>
  <path class="f" d="M10.4 11.2h7.2v1.6h-7.2Z" opacity=".55"/>
</symbol>
<symbol id="t-pc" viewBox="0 0 24 24">
  <rect x="2.8" y="3.8" width="18.4" height="12.6" rx="2.2"/>
  <path d="M12 16.4v3.6M8.4 20h7.2"/>
  <path class="f" d="M4.8 5.8h14.4v8.6H4.8Z"/>
</symbol>
<symbol id="t-laptop" viewBox="0 0 24 24">
  <rect x="5" y="4.8" width="14" height="10" rx="1.9"/>
  <path d="M2.4 18.6h19.2l-1.5-2.6H3.9Z"/>
  <path class="f" d="M6.6 6.4h10.8v7H6.6Z"/>
</symbol>
<symbol id="t-phone" viewBox="0 0 24 24">
  <rect x="7.2" y="2.4" width="9.6" height="19.2" rx="2.6"/>
  <path d="M10.4 5.2h3.2"/>
  <circle cx="12" cy="18.6" r=".95" class="f"/>
  <path class="f" d="M9 7.4h6v8.4H9Z" opacity=".7"/>
</symbol>
<symbol id="t-tablet" viewBox="0 0 24 24">
  <rect x="4.4" y="2.8" width="15.2" height="18.4" rx="2.6"/>
  <circle cx="12" cy="18.4" r=".9" class="f"/>
  <path class="f" d="M6.6 5.2h10.8v11.2H6.6Z" opacity=".7"/>
</symbol>
<symbol id="t-tv" viewBox="0 0 24 24">
  <rect x="2.6" y="4.4" width="18.8" height="12.4" rx="2.2"/>
  <path d="M8.6 20.4h6.8"/>
  <path class="f" d="M4.6 6.4h14.8v8.4H4.6Z"/>
</symbol>
<symbol id="t-projector" viewBox="0 0 24 24">
  <rect x="2.4" y="6.6" width="19.2" height="10.8" rx="2.6"/>
  <circle cx="8.6" cy="12" r="2.9"/>
  <circle cx="8.6" cy="12" r="1.3" class="f"/>
  <path d="M15.2 10h3.4M15.2 14h3.4"/>
</symbol>
<symbol id="t-speaker" viewBox="0 0 24 24">
  <rect x="6.2" y="2.6" width="11.6" height="18.8" rx="5.8"/>
  <circle cx="12" cy="9.4" r="2.7" class="f"/>
  <path d="M9.2 16.6h5.6"/>
</symbol>
<symbol id="t-camera" viewBox="0 0 24 24">
  <path d="M3.8 8.2a2.2 2.2 0 0 1 2.2-2.2h5.6a2.2 2.2 0 0 1 2.2 2.2v4a2.2 2.2 0 0 1-2.2 2.2H6a2.2 2.2 0 0 1-2.2-2.2Z"/>
  <circle cx="8.8" cy="10.2" r="2.3" class="f"/>
  <path d="M8.8 14.4v3a2.4 2.4 0 0 0 2.4 2.4h5.4a2.4 2.4 0 0 0 2.4-2.4v-1.8"/>
  <path d="M17.4 12.6h2.2"/>
</symbol>
<symbol id="t-printer" viewBox="0 0 24 24">
  <path d="M7 8.2V4.4h10v3.8"/>
  <rect x="3.2" y="8.2" width="17.6" height="7.4" rx="2"/>
  <path d="M7 15.6h10v4.4H7Z"/>
  <circle cx="17.6" cy="11.2" r=".9" class="f"/>
</symbol>
<symbol id="t-router" viewBox="0 0 24 24">
  <rect x="2.8" y="12.2" width="18.4" height="7.4" rx="2.2"/>
  <path d="M7 12.2V8.4M12 12.2V6M17 12.2V8.4"/>
  <circle cx="7" cy="16" r=".95" class="f"/>
  <circle cx="10.4" cy="16" r=".95" class="f"/>
</symbol>
<symbol id="t-console" viewBox="0 0 24 24">
  <path d="M7.8 7.2h8.4a4.8 4.8 0 0 1 4.7 5.6l-.6 3.1a2.7 2.7 0 0 1-4.8 1.2L14.6 15H9.4l-.9 2.1a2.7 2.7 0 0 1-4.8-1.2l-.6-3.1A4.8 4.8 0 0 1 7.8 7.2Z"/>
  <path d="M6.8 10.2v2.6M5.5 11.5h2.6"/>
  <circle cx="16.4" cy="10.6" r="1" class="f"/>
  <circle cx="18.2" cy="12.6" r="1" class="f"/>
</symbol>
<symbol id="t-tvbox" viewBox="0 0 24 24">
  <rect x="2.8" y="9.4" width="18.4" height="7.4" rx="2.2"/>
  <path d="M12 9.4V6.2"/>
  <circle cx="12" cy="4.8" r="1.4" class="f"/>
  <circle cx="17.6" cy="13.1" r=".9" class="f"/>
  <path class="f" d="M5 11.2h5.6v3.8H5Z" opacity=".7"/>
</symbol>
<symbol id="t-watch" viewBox="0 0 24 24">
  <rect x="6.4" y="6.4" width="11.2" height="11.2" rx="3.6"/>
  <path d="M9 6.4 9.4 3h5.2l.4 3.4M9 17.6l.4 3.4h5.2l.4-3.4"/>
  <path d="M12 9.6V12l1.9 1.2"/>
</symbol>
<symbol id="t-fridge" viewBox="0 0 24 24">
  <rect x="5.2" y="2.4" width="13.6" height="19.2" rx="2.4"/>
  <path d="M5.2 9.6h13.6"/>
  <path d="M8.4 5.2v2.2M8.4 12.2v2.6"/>
</symbol>
<symbol id="t-washer" viewBox="0 0 24 24">
  <rect x="4.2" y="2.6" width="15.6" height="18.8" rx="2.4"/>
  <circle cx="12" cy="14" r="4.1"/>
  <path class="f" d="M12 9.9a4.1 4.1 0 0 1 0 8.2Z" opacity=".55"/>
  <path d="M7 6.2h2.4M15.6 6.2h1.4"/>
</symbol>
<symbol id="t-ac" viewBox="0 0 24 24">
  <rect x="2.8" y="6.6" width="18.4" height="6.4" rx="2.2"/>
  <path d="M6.4 16.2c0 1.6.9 2.5.9 3.6M12 16.2c0 1.6.9 2.5.9 3.6M17.6 16.2c0 1.6.9 2.5.9 3.6"/>
  <path class="f" d="M4.8 8.4h14.4v2.8H4.8Z" opacity=".55"/>
</symbol>
<symbol id="t-vacuum" viewBox="0 0 24 24">
  <circle cx="12" cy="13.4" r="7.6"/>
  <path d="M12 5.8v3.2"/>
  <circle cx="12" cy="13.4" r="2.5" class="f"/>
  <path d="M4.4 13.4h3.2M16.4 13.4h3.2"/>
</symbol>
<symbol id="t-light" viewBox="0 0 24 24">
  <path d="M12 2.8a6.2 6.2 0 0 0-3.4 11.4c.5.35.8.95.8 1.55v.65h5.2v-.65c0-.6.3-1.2.8-1.55A6.2 6.2 0 0 0 12 2.8Z"/>
  <path d="M9.8 19.2h4.4M10.4 21.4h3.2"/>
  <path class="f" d="M12 2.8a6.2 6.2 0 0 0-2.4 11.9h4.8A6.2 6.2 0 0 0 12 2.8Z" opacity=".5"/>
</symbol>
<symbol id="t-plug" viewBox="0 0 24 24">
  <rect x="4.2" y="3.2" width="15.6" height="17.6" rx="3.2"/>
  <circle cx="9.4" cy="10.4" r="1.5" class="f"/>
  <circle cx="14.6" cy="10.4" r="1.5" class="f"/>
  <path d="M9.2 15.6h5.6"/>
</symbol>
<symbol id="t-lock" viewBox="0 0 24 24">
  <rect x="4.4" y="9.4" width="15.2" height="11.2" rx="2.6"/>
  <path d="M7.8 9.4V7.2a4.2 4.2 0 0 1 8.4 0v2.2"/>
  <circle cx="12" cy="15" r="1.7" class="f"/>
</symbol>
<symbol id="t-cooker" viewBox="0 0 24 24">
  <rect x="3.2" y="7.8" width="17.6" height="11.4" rx="2.6"/>
  <path d="M3.2 12.2h17.6"/>
  <circle cx="17.4" cy="10" r=".95" class="f"/>
  <path d="M6.6 7.8V6h10.8v1.8"/>
</symbol>
<symbol id="t-car" viewBox="0 0 24 24">
  <path d="M3.6 14.8h16.8v2.6a1.6 1.6 0 0 1-1.6 1.6H5.2a1.6 1.6 0 0 1-1.6-1.6Z"/>
  <path d="M5.4 14.8 7.3 9.1a2.1 2.1 0 0 1 2-1.5h5.4a2.1 2.1 0 0 1 2 1.5l1.9 5.7"/>
  <circle cx="7.8" cy="18.2" r="1.7"/><circle cx="16.2" cy="18.2" r="1.7"/>
  <path class="f" d="M8.2 11.4h7.6l1.1 3.4H7.1Z" opacity=".55"/>
</symbol>
<symbol id="t-iot" viewBox="0 0 24 24">
  <circle cx="12" cy="12" r="2.3" class="f"/>
  <circle cx="12" cy="12" r="2.3"/>
  <path d="M7.7 7.7a6.2 6.2 0 0 0 0 8.6M16.3 7.7a6.2 6.2 0 0 1 0 8.6"/>
  <path d="M4.6 4.6a10.4 10.4 0 0 0 0 14.8M19.4 4.6a10.4 10.4 0 0 1 0 14.8"/>
</symbol>
<symbol id="t-unknown" viewBox="0 0 24 24">
  <circle cx="12" cy="12" r="9.2"/>
  <path d="M9.7 9.5a2.4 2.4 0 0 1 4.6.7c0 1.7-2.3 2-2.3 3.7"/>
  <circle cx="12" cy="17" r="1.1" class="f"/>
</symbol>

<symbol id="i-auto" viewBox="0 0 24 24">
  <circle cx="12" cy="12" r="9"/>
  <path class="f" d="M12 3a9 9 0 0 1 0 18Z"/>
</symbol>
</defs></svg>

<div class="gate hide" id="gate">
  <form class="gatebox" id="lgForm" autocomplete="on">
    <div class="lgmark"><svg viewBox="0 0 32 32" style="width:26px;height:26px"><use href="#i-mark"/></svg></div>
    <b>HiRouterCenter</b>
    <span class="gsub">登录网络控制台</span>
    <label class="efld"><span>用户名</span>
      <input class="inp" id="lgUser" name="username" value="admin" autocomplete="username"></label>
    <label class="efld"><span>密码</span>
      <input class="inp" id="lgPass" name="password" type="password"
        autocomplete="current-password" placeholder="控制台密码"></label>
    <label class="ckrow"><input type="checkbox" id="lgRemember">
      <span>保持登录（7 天）</span></label>
    <button class="btn btn-primary" id="lgBtn" type="submit">登录</button>
    <div class="gerr" id="lgErr"></div>
  </form>
</div>

<div class="shell">
  <header class="topbar">
    <button class="btn btn-sm" id="menuBtn" aria-label="打开导航" style="width:30px;height:30px;padding:0">
      <svg class="i"><use href="#i-menu"/></svg></button>
    <div class="logo"><svg viewBox="0 0 32 32" style="width:20px;height:20px"><use href="#i-mark"/></svg></div>
    <div class="brand">HiRouterCenter</div>
    <div class="ctx" id="ctx">设备</div>
    <div class="topright">
      <button class="btn" id="themeBtn" title="切换主题"><svg class="i"><use href="#i-moon"/></svg><span class="tlabel">深色</span></button>
      <button class="btn" id="btnLogout" title="退出登录"><svg class="i"><use href="#i-logout"/></svg><span class="tlabel">退出</span></button>
    </div>
  </header>

  <div class="body">
    <aside class="sidebar">
      <nav class="nav">
        <button class="ni" data-page="devices" aria-current="true">
          <svg class="i"><use href="#i-devices"/></svg><span>设备</span><span class="cnt" id="cntDev"></span></button>
        <button class="ni" data-page="firewall">
          <svg class="i"><use href="#i-fw6"/></svg><span>IPv6 防火墙</span><span class="cnt" id="cntFw"></span></button>
        <button class="ni" data-page="tasks">
          <svg class="i"><use href="#i-cal"/></svg><span>计划任务</span><span class="cnt" id="cntTask"></span></button>
        <div class="navg">系统</div>
        <button class="ni" data-page="notify">
          <svg class="i"><use href="#i-bell"/></svg><span>通知</span><span class="cnt" id="cntChan"></span></button>
        <button class="ni" data-page="router">
          <svg class="i"><use href="#i-knob"/></svg><span>路由器设置</span></button>
        <button class="ni" data-page="about">
          <svg class="i"><use href="#i-info"/></svg><span>关于</span></button>
      </nav>
      <div class="nifoot">
        <button class="ni" id="btnCollapse">
          <svg class="i"><use href="#i-chevleft"/></svg><span>收起侧栏</span></button>
      </div>
    </aside>

    <main class="main">

      <!-- ================= 设备（首页） ================= -->
      <div class="page" id="p-devices">
        <div class="phead">
          <div class="h1">设备</div>
          <div class="sub" id="devSub"></div>
          <div class="phead-right">
            <button class="btn" id="btnRefreshDev"><svg class="i"><use href="#i-refresh"/></svg>刷新</button>
          </div>
        </div>

        <div class="card" id="infoCard">
          <div class="rc-head">
            <div class="rc-mark"><svg viewBox="0 0 32 32"><use href="#i-mark"/></svg></div>
            <div class="rc-id">
              <div class="n" id="riName">路由器</div>
              <div class="m" id="riSub"></div>
            </div>
            <span class="badge badge-plain" id="riBadge"><span class="dot"></span>读取中</span>
          </div>
          <div class="rc-grid" id="riGrid"></div>
          <div class="rc-acts">
            <span class="rc-acts-t">快捷操作</span>
            <button class="btn btn-sm" data-op="reboot"><svg class="i"><use href="#i-refresh"/></svg>重启路由器</button>
            <button class="btn btn-sm" data-op="redial"><svg class="i"><use href="#i-link"/></svg>重新拨号</button>
            <button class="btn btn-sm" data-op="power"><svg class="i"><use href="#i-wifi"/></svg>功率模式 <b id="qcPowerTxt">—</b></button>
            <button class="btn btn-sm" data-op="channel"><svg class="i"><use href="#i-zap"/></svg>信道优化</button>
          </div>
        </div>

        <div class="filterrow">
          <div class="chips" id="devChips"></div>
          <select class="sel" id="devType" title="按设备类型筛选" style="width:auto;max-width:190px"></select>
          <div class="wrap-inp" style="max-width:280px;margin-left:auto">
            <svg class="i"><use href="#i-search"/></svg>
            <input class="inp" id="devQ" placeholder="设备名 / MAC / IPv6">
          </div>
        </div>

        <div class="devgrid" id="devGrid"></div>
      </div>

      <!-- ================= IPv6 防火墙 ================= -->
      <div class="page hide" id="p-firewall">
        <div class="phead">
          <div class="h1">IPv6 防火墙</div>
          <div class="sub">把设备的当前 IPv6 写进白名单，地址变了原地更新</div>
          <div class="phead-right">
            <button class="btn" id="btnRefreshFw"><svg class="i"><use href="#i-refresh"/></svg>刷新</button>
            <button class="btn" id="btnSyncNow"><svg class="i"><use href="#i-zap"/></svg>立即同步</button>
            <button class="btn btn-primary" id="btnAddRule"><svg class="i"><use href="#i-plus"/></svg>添加规则</button>
          </div>
        </div>

        <div class="card">
          <div class="fwbar">
            <div class="ico"><svg class="i" style="width:19px;height:19px"><use href="#i-fw6"/></svg></div>
            <div class="txt">
              <b>IPv6 防火墙</b>
              <span>关闭后白名单整体不生效，同步会暂停</span>
            </div>
            <span class="badge badge-plain" id="fwBadge"><span class="dot"></span>读取中</span>
            <button class="sw" id="fwSw" data-on="false" style="margin-left:6px" aria-label="IPv6 防火墙总开关"></button>
          </div>
          <div class="rc-grid" id="fwKv" style="border-bottom:0"></div>
        </div>

        <div class="card">
          <div class="ch"><svg class="i"><use href="#i-fw6"/></svg><span>白名单规则</span>
            <span class="hint">规则跟着设备走，地址一变自动原地更新</span></div>
          <div class="tblwrap">
            <table class="tbl tbl-fixed">
              <thead><tr>
                <th style="width:150px">服务名称</th>
                <th style="width:170px">设备</th>
                <th style="width:200px">当前地址</th>
                <th style="width:100px">放行端口</th>
                <th style="width:130px">允许来源</th>
                <th style="width:120px">当前状态</th>
                <th style="width:110px"></th>
              </tr></thead>
              <tbody id="ruleRows"></tbody>
            </table>
          </div>
        </div>

        <div class="card">
          <div class="ch"><svg class="i"><use href="#i-link"/></svg><span>路由器白名单条目</span>
            <span class="hint" id="entHint"></span></div>
          <div class="tblwrap">
            <table class="tbl tbl-fixed">
              <thead><tr>
                <th style="width:180px">条目名称</th>
                <th>本机 / 地址</th>
                <th style="width:90px">端口</th>
                <th style="width:140px">允许来源</th>
                <th style="width:140px"></th>
              </tr></thead>
              <tbody id="entRows"></tbody>
            </table>
          </div>
        </div>

        <div class="card">
          <div class="ch"><svg class="i"><use href="#i-history"/></svg><span>同步记录</span>
            <span class="hint">只在真正改动白名单时记一条</span></div>
          <div class="cb" style="padding-bottom:0">
            <div class="filterrow" style="margin-bottom:12px">
              <div class="wrap-inp" style="max-width:240px">
                <svg class="i"><use href="#i-search"/></svg>
                <input class="inp" id="evQ" placeholder="搜索设备名 / 地址…">
              </div>
              <select class="sel" id="evKind" style="width:auto">
                <option value="">全部动作</option><option value="created">新增</option>
                <option value="updated">更新</option><option value="removed">删除</option>
                <option value="fw">开关</option>
              </select>
              <span class="sub">保留上限</span>
              <select class="sel" id="evMax" style="width:auto"></select>
              <span class="sub">条（<span id="evCount">0</span> 条）</span>
              <button class="btn btn-sm btn-danger" id="btnEvClear" style="margin-left:auto">
                <svg class="i"><use href="#i-trash"/></svg>清空记录</button>
            </div>
          </div>
          <div class="tblwrap">
            <table class="tbl tbl-fixed">
              <thead><tr>
                <th style="width:160px">时间</th>
                <th style="width:88px">动作</th>
                <th style="width:190px">设备</th>
                <th>变化</th>
              </tr></thead>
              <tbody id="evRows"></tbody>
            </table>
          </div>
        </div>
      </div>

      <!-- ================= 计划任务 ================= -->
      <div class="page hide" id="p-tasks">
        <div class="phead">
          <div class="h1">计划任务</div>
          <div class="sub" id="taskSub"></div>
          <div class="phead-right">
            <button class="btn btn-primary" id="btnAddTask"><svg class="i"><use href="#i-plus"/></svg>添加任务</button>
          </div>
        </div>

        <div class="card">
          <div class="ch"><svg class="i"><use href="#i-cal"/></svg><span>任务列表</span>
            <span class="hint" id="taskTz"></span></div>
          <div class="tblwrap">
            <table class="tbl tbl-fixed">
              <thead><tr>
                <th style="width:120px">任务</th>
                <th style="width:110px">类型</th>
                <th style="width:200px">执行时间</th>
                <th style="width:110px">下次</th>
                <th style="width:190px">上次结果</th>
                <th style="width:56px">启用</th>
                <th style="width:196px"></th>
              </tr></thead>
              <tbody id="taskRows"></tbody>
            </table>
          </div>
        </div>
      </div>

      <!-- ================= 通知 ================= -->
      <div class="page hide" id="p-notify">
        <div class="phead">
          <div class="h1">通知</div>
          <div class="sub" id="nSub"></div>
          <div class="phead-right">
            <button class="btn btn-sm btn-primary" id="nBtnAdd">
              <svg class="i"><use href="#i-plus"/></svg>添加渠道</button>
            <button class="btn btn-sm hide" id="nBtnNone">全部关闭</button>
            <button class="btn btn-sm hide" id="nBtnRec">恢复推荐</button>
            <button class="btn btn-sm btn-danger hide" id="nBtnClear">
              <svg class="i"><use href="#i-trash"/></svg>清空</button>
          </div>
        </div>

        <div class="filterrow">
          <div class="seg" id="nSeg">
            <button data-t="channels" data-on="true">渠道</button>
            <button data-t="events">事件订阅</button>
            <button data-t="history">推送历史</button>
          </div>
        </div>

        <div id="n-tab-channels" style="display:flex;flex-direction:column;gap:14px">
          <div class="card">
            <div class="ch"><svg class="i"><use href="#i-bell"/></svg><span>通知渠道</span>
              <span class="hint" id="chanHint"></span></div>
            <div id="chanRows"></div>
          </div>

          <div class="card">
            <div class="ch"><svg class="i"><use href="#i-knob"/></svg><span>投递策略</span></div>
            <div class="cb" style="padding-top:4px;padding-bottom:4px">
              <div class="fieldrow">
                <div class="t"><b>启用通知</b><span>总开关。关闭后不发送任何消息，也不写推送历史</span></div>
                <div class="ctl"><button class="sw" id="polEnabled" data-on="true"></button></div>
              </div>
              <div class="fieldrow">
                <div class="t"><b>静默时段</b><span>支持跨天，例如 23:00–07:00；标注「紧急」的事件照常发送</span></div>
                <div class="ctl" style="display:flex;align-items:center;gap:8px">
                  <button class="sw" id="polQuietSw" data-on="false"></button>
                  <input class="inp" type="time" id="polQuietFrom" value="23:00" style="width:112px">
                  <span class="dash">–</span>
                  <input class="inp" type="time" id="polQuietTo" value="07:00" style="width:112px">
                </div>
              </div>
              <div class="fieldrow">
                <div class="t"><b>同设备同事件去重窗口</b><span>设备频繁上下线时，靠这个窗口压住重复消息</span></div>
                <div class="ctl" style="display:flex;align-items:center;gap:8px">
                  <input class="inp" type="number" id="polDedupe" min="0" max="1440" value="5" style="width:88px">
                  <span class="sub">分钟</span>
                </div>
              </div>
              <div class="fieldrow">
                <div class="t"><b>推送历史保留</b><span>默认保留最近 50 条，最多 200 条；只留在本机 /data 下，超出后自动删最旧的</span></div>
                <div class="ctl" style="width:160px"><select class="sel" id="polHist"></select></div>
              </div>
            </div>
          </div>
        </div>

        <div id="n-tab-events" style="display:none;flex-direction:column;gap:14px">
          <div class="banner banner-info">
            <svg class="i"><use href="#i-info"/></svg>
            <span>标题由事件自动生成，不用自己写。开启某个事件后，它会同时发往所有已启用的渠道。</span>
          </div>
          <div class="card">
            <div class="ch"><svg class="i"><use href="#i-fw6"/></svg><span>IPv6 防火墙</span>
              <span class="hint" data-g="fw"></span></div>
            <div id="evg-fw"></div>
          </div>
          <div class="card">
            <div class="ch"><svg class="i"><use href="#i-devices"/></svg><span>设备</span>
              <span class="hint" data-g="dev"></span></div>
            <div id="evg-dev"></div>
          </div>
          <div class="card">
            <div class="ch"><svg class="i"><use href="#i-cal"/></svg><span>计划任务</span>
              <span class="hint" data-g="task"></span></div>
            <div id="evg-task"></div>
          </div>
          <div class="card">
            <div class="ch"><svg class="i"><use href="#i-alert"/></svg><span>系统</span>
              <span class="hint" data-g="sys"></span></div>
            <div id="evg-sys"></div>
          </div>
        </div>

        <div id="n-tab-history" style="display:none">
          <div class="card">
            <div class="ch"><svg class="i"><use href="#i-history"/></svg><span>推送历史</span>
              <span class="hint" id="histHint"></span></div>
            <div class="tblwrap">
              <table class="tbl tbl-fixed">
                <thead><tr>
                  <th style="width:130px">时间</th>
                  <th style="width:120px">渠道</th>
                  <th style="width:190px">标题</th>
                  <th style="width:80px">结果</th>
                  <th>正文</th>
                </tr></thead>
                <tbody id="histRows"></tbody>
              </table>
            </div>
          </div>
        </div>
      </div>

      <!-- ================= 路由器设置 ================= -->
      <div class="page hide" id="p-router">
        <div class="phead">
          <div class="h1">路由器设置</div>
          <div class="sub" id="routerSub"></div>
          <div class="phead-right">
            <button class="btn" id="btnTest"><svg class="i"><use href="#i-zap"/></svg>测试连接</button>
            <button class="btn btn-primary" id="btnSaveSettings">保存</button>
          </div>
        </div>
        <div class="card">
          <div class="ch"><svg class="i"><use href="#i-link"/></svg><span>路由器连接</span>
            <span class="badge badge-plain" id="connBadge" style="margin-left:auto;font-weight:400">
              <span class="dot"></span>未知</span></div>
          <div class="cb" id="routerFields"></div>
        </div>
        <div class="card">
          <div class="ch"><svg class="i"><use href="#i-knob"/></svg><span>运行行为</span></div>
          <div class="cb" id="behaviorFields"></div>
        </div>
      </div>

      <!-- ================= 关于 ================= -->
      <div class="page hide" id="p-about">
        <div class="phead">
          <div class="h1">关于</div>
          <div class="sub">HiRouterCenter v__APP_VERSION__</div>
        </div>

        <div class="card">
          <div class="ch"><svg class="i"><use href="#i-info"/></svg><span>HiRouterCenter</span>
            <span class="hint">v__APP_VERSION__</span></div>
          <div class="cb">
            <p class="sub" style="margin:0 0 12px">
              让局域网设备的公网 IPv6 访问不因地址变化而中断：自动跟踪设备的当前 IPv6，
              同步写入路由器的 IPv6 防火墙白名单并按需放行端口，外网直连不再受地址变化影响。
            </p>
            <div style="display:grid;gap:7px;font-size:12.5px;color:var(--text-3)">
              <div>· <b style="color:var(--text-2)">按设备维护</b> —— 白名单里选设备即放行，之后地址一变自动原地更新</div>
              <div>· <b style="color:var(--text-2)">自动取址</b> —— 取路由器记录的最新地址；设备离线时自动跳过，不误删</div>
              <div>· <b style="color:var(--text-2)">设备总览</b> —— 在线 / 离线 / 黑名单 / 儿童上网一屏看全，每个地址点一下即复制</div>
              <div>· <b style="color:var(--text-2)">快捷操作</b> —— 重启、重拨、功率模式、信道优化，点一下就能做</div>
              <div>· <b style="color:var(--text-2)">计划任务</b> —— 定时重启 / 重拨 / 功率模式 / 信道优化 / 定时唤醒</div>
              <div>· <b style="color:var(--text-2)">事件通知</b> —— 11 种渠道 + 自定义 Webhook，按事件订阅，标题自动生成</div>
            </div>
          </div>
        </div>

        <div class="card">
          <div class="ch"><svg class="i"><use href="#i-github"/></svg><span>作者与项目</span>
            <span class="hint">MIT License · 开源免费</span></div>
          <div class="cb">
            <div class="authrow">
              <div class="avatar">AZ</div>
              <div class="t">
                <b>Aaron_Z</b>
                <span>HiRouterCenter 作者 · 项目完全开源，欢迎提 Issue 与 Pull Request</span>
              </div>
            </div>
            <a class="lnk" href="https://github.com/aaron2024S/ipv6sync" target="_blank" rel="noopener">
              <svg class="i"><use href="#i-github"/></svg>
              <span>GitHub 项目主页</span>
              <em class="u">github.com/aaron2024S/ipv6sync</em>
              <svg class="i go"><use href="#i-out"/></svg>
            </a>
            <a class="lnk" href="https://github.com/aaron2024S/ipv6sync/issues" target="_blank" rel="noopener">
              <svg class="i"><use href="#i-issue"/></svg>
              <span>问题反馈 / 功能建议</span>
              <em class="u">issues</em>
              <svg class="i go"><use href="#i-out"/></svg>
            </a>
            <a class="lnk" href="https://github.com/aaron2024S/ipv6sync/releases" target="_blank" rel="noopener">
              <svg class="i"><use href="#i-tag"/></svg>
              <span>版本更新记录</span>
              <em class="u">releases</em>
              <svg class="i go"><use href="#i-out"/></svg>
            </a>
            <div class="lnk plain" style="margin-top:9px">
              <svg class="i"><use href="#i-copy"/></svg>
              <span>Docker 镜像</span>
              <em class="u">aaron2024s/ipv6sync:latest</em>
              <button class="btn btn-sm" id="btnCopyImage" style="margin-left:8px">复制</button>
            </div>
          </div>
        </div>

        <div class="card">
          <div class="ch"><svg class="i"><use href="#i-history"/></svg><span>维护</span>
            <span class="hint">累计写入次数跨容器重启保存，只在需要时清零</span></div>
          <div class="cb">
            <div class="maint-row">
              <button class="btn" id="btnResetCounters">重置累计写入</button>
              <span class="hint" id="countersTxt">—</span>
            </div>
          </div>
        </div>

        <div class="card">
          <div class="ch"><svg class="i"><use href="#i-alert"/></svg><span>诊断信息</span>
            <span class="hint">排障时把这段发出来即可定位问题</span>
            <button class="btn btn-sm" id="btnCopyDiag" style="margin-left:8px">复制</button></div>
          <div class="cb">
            <pre class="mono" id="diagPre" style="margin:0;max-height:260px;overflow:auto;border:1px solid var(--line-2);
              border-radius:10px;background:var(--ink-800);padding:12px;font-size:11.5px;
              line-height:1.7;color:var(--text-3)"></pre>
          </div>
        </div>
      </div>

    </main>
  </div>
</div>

<div class="toasts" id="toasts"></div>

<script>
/* ==========================================================================
   HiRouterCenter 前端：零依赖、零构建。所有数据都来自 /api/*，没有任何模拟数据。
   ========================================================================== */

/* ---------------- 基础工具 ---------------- */
const $ = s => document.querySelector(s);
const $$ = s => Array.from(document.querySelectorAll(s));
function el(tag, cls, html) {
  const d = document.createElement(tag);
  if (cls) d.className = cls;
  if (html != null) d.innerHTML = html;
  return d;
}
function svgI(id, cls) { return '<svg class="i ' + (cls || '') + '"><use href="#i-' + id + '"/></svg>'; }
function escHtml(s) {
  return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}
function escAttr(s) { return escHtml(s).replace(/"/g, '&quot;'); }
function toast(title, sub, icon) {
  const box = $('#toasts');
  const t = el('div', 'toast', '<svg class="i"><use href="#i-' + (icon || 'check') + '"/></svg>'
    + '<div><b>' + escHtml(title) + '</b>' + (sub ? '<span>' + escHtml(sub) + '</span>' : '') + '</div>');
  box.appendChild(t);
  setTimeout(() => t.remove(), 3000);
}
function errToast(r) { toast('操作没成功', (r && r.error) || '请稍后重试', 'alert'); }

/* 复制：navigator.clipboard 只在 https / localhost 下可用，
   NAS 上基本都是 http://192.168.x.x，必须回退 execCommand。 */
function copyText(text) {
  const s = String(text || '');
  if (!s) return false;
  if (navigator.clipboard && window.isSecureContext) {
    navigator.clipboard.writeText(s).catch(() => fallbackCopy(s));
    return true;
  }
  return fallbackCopy(s);
}
function fallbackCopy(s) {
  const ta = document.createElement('textarea');
  ta.value = s;
  ta.style.cssText = 'position:fixed;top:-1000px;opacity:0';
  document.body.appendChild(ta);
  ta.select();
  let ok = false;
  try { ok = document.execCommand('copy'); } catch (e) { ok = false; }
  ta.remove();
  return ok;
}

/* ---------------- 接口层 ---------------- */
async function api(path, body) {
  const opt = body === undefined ? {} :
    { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) };
  const r = await fetch(path, opt);
  if (r.status === 401) { showGate(); throw new Error('未登录'); }
  let j = null;
  try { j = await r.json(); } catch (e) { j = { ok: false, error: '返回内容无法解析' }; }
  return j;
}

/* ---------------- 全局状态 ---------------- */
const S = {
  authed: false, version: '',
  state: null, tasks: null, events: null, notify: null,
  info: null, hosts: null, wl: null, hist: null,
  devFilter: 'all', devQuery: '', devType: 'all',
  page: 'devices', nTab: 'channels',
  loaded: {},          // 每页最后一次拉数据的时间，用来做缓存
};

/* ---------------- 登录 ---------------- */
function showGate() {
  S.authed = false;
  $('#gate').classList.remove('hide');
  setTimeout(() => { const p = $('#lgPass'); if (p) p.focus(); }, 60);
}
function hideGate() { $('#gate').classList.add('hide'); }

try { localStorage.removeItem('ipv6sync-remember'); } catch (e) { }
$('#lgForm').addEventListener('submit', async e => {
  e.preventDefault();
  const btn = $('#lgBtn'), err = $('#lgErr');
  err.textContent = '';
  btn.disabled = true;
  try {
    const r = await fetch('/api/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        user: $('#lgUser').value,
        password: $('#lgPass').value,
        // 勾了「保持登录（7 天）」由后端签发 7 天有效期的 HttpOnly Cookie；
        // 浏览器本地不保存任何密码明文（顺手清掉旧版本遗留的明文记录）
        remember: !!$('#lgRemember').checked,
      }),
    });
    const j = await r.json().catch(() => ({}));
    if (r.ok && j.ok) {
      hideGate();
      $('#lgPass').value = '';
      S.authed = true;
      await boot();
    } else {
      err.textContent = j.error || '登录失败';
    }
  } catch (e) {
    err.textContent = '连不上服务，请稍后再试';
  } finally { btn.disabled = false; }
});
$('#btnLogout').addEventListener('click', async () => {
  try { await api('/api/logout', {}); } catch (e) { /* 已掉线也算退出 */ }
  S.authed = false;
  showGate();
});

/* ---------------- 设备类型 ---------------- */
const TYPES = [
  ['nas', 'NAS / 存储'], ['pc', '台式机'], ['laptop', '笔记本'], ['phone', '手机'],
  ['tablet', '平板'], ['watch', '手表 / 手环'], ['tv', '电视'], ['projector', '投影仪'],
  ['tvbox', '机顶盒'], ['speaker', '音箱'], ['camera', '摄像头'], ['printer', '打印机'],
  ['router', '路由器 / AP'], ['console', '游戏机'], ['fridge', '冰箱'], ['washer', '洗衣机'],
  ['ac', '空调'], ['vacuum', '扫地机'], ['light', '灯'], ['plug', '插座 / 开关'],
  ['lock', '门锁'], ['cooker', '厨房电器'], ['car', '车机'], ['iot', '传感器 / 网关'],
  ['unknown', '未知设备'],
];
const TYPE_NAME = Object.fromEntries(TYPES);
function tIcon(t) { return '<svg class="i"><use href="#t-' + (TYPE_NAME[t] ? t : 'unknown') + '"/></svg>'; }
function typeOf(d) { return d.type || d.t || 'unknown'; }

/* ---------------- 通用格式化 ---------------- */
function ago(ts) {
  if (!ts) return '—';
  const t = new Date(String(ts).replace(' ', 'T')).getTime();
  if (!t) return ts;
  const d = Math.max(0, Math.floor((Date.now() - t) / 1000));
  if (d < 60) return d + ' 秒前';
  if (d < 3600) return Math.floor(d / 60) + ' 分钟前';
  if (d < 86400) return Math.floor(d / 3600) + ' 小时前';
  return Math.floor(d / 86400) + ' 天前';
}
function hhmm(ts) { return ts ? String(ts).slice(11, 16) : ''; }
/* 当前的检测周期（秒）：设置层里的 POLL_INTERVAL，取不到就按 60 */
function pollInterval() {
  const f = ((S.state && S.state.settings) || []).flatMap(g => g.fields || [])
    .find(x => x.key === 'POLL_INTERVAL');
  const n = f ? Number(f.value) : NaN;
  return Number.isFinite(n) && n > 0 ? n : 60;
}

/* ==========================================================================
   设备页
   ========================================================================== */
async function loadInfo() {
  try { S.info = await api('/api/router/info'); } catch (e) { S.info = { ok: false }; }
  renderInfo();
}
async function loadHosts() {
  try { S.hosts = await api('/api/router/hosts'); } catch (e) { S.hosts = { ok: false }; }
  renderDevices();
  renderCounts();
  renderTypeFilter();
}
function renderInfo() {
  const box = $('#riName'), sub = $('#riSub'), badge = $('#riBadge'), grid = $('#riGrid');
  const info = (S.info && S.info.info) || {};
  const ok = !!(S.info && S.info.ok);
  box.textContent = info.product || (ok ? '路由器' : '读不到路由器信息');
  sub.textContent = [info.model, S.state && S.state.overview && S.state.overview.router_host,
    info.hardware && ('硬件 ' + info.hardware)].filter(Boolean).join(' · ');
  badge.className = 'badge ' + (ok ? 'badge-run' : 'badge-err');
  badge.innerHTML = '<span class="dot"></span>' + (ok ? '在线' : '未连接');

  const st = (S.state && S.state.status) || {};
  const ssid = info.ssid || {};
  const ssidHtml = Object.keys(ssid).length
    ? '<span class="two">' + Object.entries(ssid).map(([k, v]) =>
      '<i><em>' + escHtml(k) + '</em>' + escHtml(v) + '</i>').join('') + '</span>'
    : '—';
  const cells = [
    ['运行时长', escHtml(info.uptime || '—')],
    ['WAN IPv4', info.wan4
      ? '<button class="cp" data-cp="' + escAttr(info.wan4) + '">' + svgI('copy')
        + '<span>' + escHtml(info.wan4) + '</span></button>' : '—'],
    ['WAN IPv6', info.wan6
      ? '<button class="cp" data-cp="' + escAttr(info.wan6) + '">' + svgI('copy')
        + '<span>' + escHtml(info.wan6) + '</span></button>' : '—'],
    ['Wi-Fi 名称', ssidHtml],
    ['在线设备', (S.info && S.info.hosts_total)
      ? escHtml(S.info.hosts_online + ' / ' + S.info.hosts_total + ' 台') : '—'],
    ['IPv6 白名单', (() => {
      const n = (S.wl && S.wl.ok) ? (S.wl.rules || []).length
        : ((S.state && S.state.overview && (S.state.overview.rules || []).length) || 0);
      return n || (S.wl && S.wl.ok) ? escHtml(n + ' 条') : '—';
    })()
      + (st.firewall_ipv6_enabled === true
        ? ' <span class="badge badge-run" style="font-weight:400;margin-left:2px"><span class="dot"></span>已开启</span>'
        : st.firewall_ipv6_enabled === false
          ? ' <span class="badge badge-plain" style="font-weight:400;margin-left:2px"><span class="dot"></span>已关闭</span>'
          : '')],
    ['上次同步', escHtml(ago(st.last_success_at))],
    ['固件版本', escHtml(info.firmware || '—')],
  ];
  grid.innerHTML = cells.map(([k, v]) =>
    '<div class="kv"><div class="k">' + k + '</div><div class="v mono">' + v + '</div></div>').join('');
  $$('#riGrid .cp').forEach(bindCopy);
  const pm = info.power_mode;
  const names = { 0: '睡眠', 1: '一般', 2: '穿墙' };
  $('#qcPowerTxt').textContent = (pm === 0 || pm === 1 || pm === 2) ? names[pm] : '—';
  if (S.hosts && S.hosts.power_mode != null && !info.power_mode) {
    const m = S.hosts.power_mode;
    if (m === 0 || m === 1 || m === 2) $('#qcPowerTxt').textContent = names[m];
  }
}
function bindCopy(b) {
  b.addEventListener('click', () => {
    const v = b.dataset.cp;
    const old = b.innerHTML;
    if (copyText(v)) {
      b.classList.add('done');
      b.innerHTML = svgI('check') + '<span>已复制</span>';
      toast('已复制到剪贴板', v, 'check');
      setTimeout(() => { b.classList.remove('done'); b.innerHTML = old; }, 1400);
    } else toast('复制失败', '长按地址手动复制', 'alert');
  });
}
function devRows() {
  const h = S.hosts;
  if (!h || !h.ok) return [];
  return h.hosts || [];
}
function visibleHosts() {
  const q = S.devQuery.trim().toLowerCase();
  const bl = new Set(((S.hosts && S.hosts.blacklist) || []).map(x => (x.mac || '').toUpperCase()));
  return devRows().filter(d => {
    const black = bl.has((d.mac || '').toUpperCase());
    if (S.devFilter === 'online' && !d.active) return false;
    if (S.devFilter === 'offline' && d.active) return false;
    if (S.devFilter === 'black' && !black) return false;
    if (S.devFilter === 'kids' && !d.kids) return false;
    if (S.devType !== 'all' && typeOf(d) !== S.devType) return false;
    if (!q) return true;
    return (d.name + d.mac + (d.ipv4 || '') + (d.ipv6 || []).join(' ')).toLowerCase().includes(q);
  });
}
function ruleOf(mac) {
  const rules = (S.hosts && S.hosts.rules) || [];
  const m = String(mac || '').toUpperCase();
  return rules.find(r => String(r.mac || '').toUpperCase() === m) || null;
}
function renderDevices() {
  const grid = $('#devGrid');
  const h = S.hosts;
  if (!h) { grid.innerHTML = '<div class="card"><div class="cb sub">正在读取设备列表…</div></div>'; return; }
  if (!h.ok) {
    grid.innerHTML = '<div class="card"><div class="cb sub">' + escHtml(h.error || '读不到设备列表')
      + '</div></div>';
    return;
  }
  const bl = new Set(((h.blacklist) || []).map(x => (x.mac || '').toUpperCase()));
  const list = visibleHosts();
  grid.innerHTML = '';
  for (const d of list) {
    const black = bl.has(String(d.mac || '').toUpperCase());
    const card = el('div', 'dev' + (d.active ? '' : ' off') + (black ? ' black' : ''));
    const head = el('div', 'dev-head');
    const av = el('button', 'avatar', tIcon(typeOf(d)));
    av.type = 'button';
    av.title = '设备类型：' + (TYPE_NAME[typeOf(d)] || '未知') + '（点击修改）';
    av.addEventListener('click', () => pickType(d));
    head.appendChild(av);
    const id = el('div', 'dev-id');
    id.appendChild(el('div', 'n', escHtml(d.name || '未知设备')));
    id.appendChild(el('div', 'm', escHtml(d.mac || '')));
    head.appendChild(id);
    head.appendChild(el('div', '', black
      ? '<span class="badge badge-warn"><span class="dot"></span>黑名单</span>'
      : (d.active ? '<span class="badge badge-run"><span class="dot"></span>在线</span>'
        : '<span class="badge badge-stop"><span class="dot"></span>离线</span>')));
    card.appendChild(head);

    const tags = el('div', 'dev-tags');
    if (black) tags.innerHTML += '<span class="badge badge-warn">已阻断上网</span>';
    if (d.kids) tags.innerHTML += '<span class="badge badge-accent">儿童上网</span>';
    if (tags.innerHTML) card.appendChild(tags);

    /* IPv4（点击复制）+ 离线设备的最后在线时间 —— 改版时丢掉的两个字段 */
    const meta = el('div', 'dev-meta');
    if (d.ipv4) {
      const b4 = el('button', 'v6', svgI('copy') + '<span>' + escHtml(d.ipv4) + '</span>');
      b4.title = '点击复制 IPv4 地址';
      b4.addEventListener('click', () => {
        const old = b4.innerHTML;
        if (copyText(d.ipv4)) {
          b4.classList.add('copied');
          b4.innerHTML = svgI('check') + '<span>已复制</span>';
          toast('已复制到剪贴板', d.ipv4, 'check');
          setTimeout(() => { b4.classList.remove('copied'); b4.innerHTML = old; }, 1400);
        } else toast('复制失败', '长按地址手动复制', 'alert');
      });
      meta.appendChild(b4);
    }
    if (!d.active && d.offline_at) {
      meta.appendChild(el('div', 'laston', svgI('history') + '最后在线 ' + escHtml(d.offline_at)));
    }
    if (meta.children.length) card.appendChild(meta);

    const v6 = el('div', 'dev-v6');
    const addrs = d.ipv6 || [];
    if (!addrs.length) v6.innerHTML = '<span class="sub" style="font-size:11.5px">没有 IPv6 地址</span>';
    addrs.forEach((a, i) => {
      const b = el('button', 'v6', svgI('copy') + '<span' + (i === 0 ? ' class="first"' : '') + '>'
        + escHtml(a) + '</span>');
      b.title = '点击复制这条地址';
      b.addEventListener('click', () => {
        const old = b.innerHTML;
        if (copyText(a)) {
          b.classList.add('copied');
          b.innerHTML = svgI('check') + '<span>已复制</span>';
          toast('已复制到剪贴板', a, 'check');
          setTimeout(() => { b.classList.remove('copied'); b.innerHTML = old; }, 1400);
        } else toast('复制失败', '长按地址手动复制', 'alert');
      });
      v6.appendChild(b);
    });
    card.appendChild(v6);

    const r = ruleOf(d.mac);
    const foot = el('div', 'dev-foot');
    foot.innerHTML = r
      ? '<span class="fw on">' + svgI('fw6') + '已放行 <b>' + escHtml(r.port) + '</b></span>'
      : '<span class="fw">' + svgI('fw6') + '未放行</span>';
    const wb = el('button', 'btn btn-sm', svgI('power') + '唤醒');
    wb.type = 'button';
    if (d.active) { wb.disabled = true; wb.title = '设备在线，不需要唤醒'; }
    wb.addEventListener('click', () => wake(d));
    foot.appendChild(wb);
    card.appendChild(foot);
    grid.appendChild(card);
  }
  if (!list.length) {
    grid.innerHTML = '<div class="card"><div class="cb sub">'
      + (devRows().length ? '没有匹配的设备' : '路由器设备列表是空的') + '</div></div>';
  }
}
async function wake(d) {
  const r = await api('/api/wol', { mac: d.mac, ipv4: d.ipv4 || '' }).catch(() => null);
  if (!r) return errToast({ error: '请求没发出去' });
  if (r.throttled) return toast('刚发过', (r.msg || '10 秒内同一台只发一次'), 'clock');
  if (r.ok) toast('唤醒包已发出', (d.name || d.mac) + ' · 开机需要点时间', 'power');
  else errToast(r);
}
function renderCounts() {
  const rows = devRows();
  const h = S.hosts;
  if (S.hosts && S.hosts.ok) {
    const bl = new Set(((h.blacklist) || []).map(x => (x.mac || '').toUpperCase()));
    const online = rows.filter(d => d.active).length;
    const kids = rows.filter(d => d.kids).length;
    const black = rows.filter(d => bl.has(String(d.mac || '').toUpperCase())).length;
    const chips = [
      ['all', '全部', rows.length], ['online', '在线', online],
      ['offline', '离线', rows.length - online], ['black', '黑名单', black],
      ['kids', '儿童上网', kids],
    ];
    $('#devChips').innerHTML = chips.map(([f, n, c]) =>
      '<button class="chip" data-f="' + f + '"' + (S.devFilter === f ? ' data-on="true"' : '')
      + '>' + n + ' <span class="n">' + c + '</span></button>').join('');
    $$('#devChips .chip').forEach(b => b.addEventListener('click', () => {
      S.devFilter = b.dataset.f;
      renderCounts(); renderDevices();
    }));
  }
  const st = (S.state && S.state.status) || {};
  $('#cntDev').textContent = rows.length || '';
  $('#cntFw').textContent = S.wl ? (S.wl.rules || []).length : '';
  $('#cntTask').textContent = S.tasks ? (S.tasks.tasks || []).length : '';
  $('#cntChan').textContent = S.notify ? (S.notify.channels || []).length : '';
  $('#devSub').textContent = st.last_error
    ? ('上次同步失败：' + st.last_error) : '';
}
function renderTypeFilter() {
  const sel = $('#devType');
  const cnt = {};
  devRows().forEach(d => { const t = typeOf(d); cnt[t] = (cnt[t] || 0) + 1; });
  const ids = Object.keys(cnt).sort((a, b) => cnt[b] - cnt[a]);
  sel.innerHTML = '<option value="all">全部类型（' + devRows().length + '）</option>'
    + ids.map(t => '<option value="' + t + '">' + (TYPE_NAME[t] || t) + '（' + cnt[t] + '）</option>').join('');
  if (S.devType !== 'all' && !cnt[S.devType]) S.devType = 'all';
  sel.value = S.devType;
}
function pickType(d) {
  const cur = typeOf(d);
  const mask = el('div', 'tpick-mask');
  const box = el('div', 'tpick');
  box.innerHTML = '<div class="th">' + tIcon(cur)
    + '<span>选择设备类型</span><button class="btn btn-sm" type="button">关闭</button></div>'
    + '<div class="tn">' + escHtml((d.name || '') + ' · ' + (d.mac || '')) + '</div>'
    + '<div class="tgrid"></div>';
  const grid = box.querySelector('.tgrid');
  for (const [id, name] of TYPES) {
    const b = el('button', 'tcell', tIcon(id) + '<span>' + name + '</span>');
    b.type = 'button';
    if (id === cur) b.dataset.on = 'true';
    b.addEventListener('click', async () => {
      close();
      const r = await api('/api/host/type', { mac: d.mac, type: id }).catch(() => null);
      if (!r || !r.ok) return errToast(r);
      d.type = id; d.type_manual = true;
      renderDevices(); renderTypeFilter();
      toast('已设为「' + name + '」', '自动识别只用来猜，你指定的会一直生效', 'check');
    });
    grid.appendChild(b);
  }
  function close() { mask.remove(); document.removeEventListener('keydown', onKey); }
  function onKey(e) { if (e.key === 'Escape') close(); }
  box.querySelector('.btn').addEventListener('click', close);
  mask.addEventListener('click', e => { if (e.target === mask) close(); });
  document.addEventListener('keydown', onKey);
  mask.appendChild(box);
  document.body.appendChild(mask);
}

/* ---------------- 路由器快捷操作 ---------------- */
const QUICK_OPS = {
  reboot: { t: '重启路由器', i: 'refresh', danger: 1, ok: '确认重启',
    d: '路由器会重启，家里所有设备都会断网，大约 1–3 分钟恢复。重启后自动继续同步。' },
  redial: { t: '重新拨号', i: 'link', ok: '确认重拨',
    d: '断开当前宽带连接再重新拨号，公网 IP 可能会变，大约 20–60 秒。' },
  power: { t: 'Wi-Fi 功率模式', i: 'wifi', ok: '切换',
    d: '功率模式决定覆盖范围和耗电，换完立即生效。' },
  channel: { t: '信道优化', i: 'zap', ok: '开始优化',
    d: '自动挑一个干扰最小的信道，稍等片刻就好。' },
};
const POWER_MODES = [
  [0, '睡眠模式', '覆盖范围最小，夜里更省电'],
  [1, '一般模式', '日常默认'],
  [2, '穿墙模式', '覆盖最远，穿墙更强'],
];
function quickOp(kind) {
  const cfg = QUICK_OPS[kind];
  const info = (S.info && S.info.info) || {};
  let cur = info.power_mode;
  if (cur == null && S.hosts) cur = S.hosts.power_mode;
  const mask = el('div', 'tpick-mask');
  const box = el('div', 'qdlg');
  let body = '<p>' + cfg.d + '</p>';
  if (kind === 'power') {
    body += '<div class="opts">' + POWER_MODES.map(([v, n, s]) =>
      '<button class="opt" type="button" data-v="' + v + '"' + (v === cur ? ' data-on="true"' : '') + '>'
      + '<span class="rd"></span><span class="ot"><b>' + n + '</b><span>' + s + '</span></span></button>').join('')
      + '</div>';
  }
  box.innerHTML = '<div class="th">' + svgI(cfg.i) + '<span>' + cfg.t + '</span>'
    + '<button class="btn btn-sm" type="button" data-a="x">关闭</button></div>'
    + '<div class="qbody">' + body + '</div>'
    + '<div class="efoot"><button class="btn" type="button" data-a="x">取消</button>'
    + '<button class="btn ' + (cfg.danger ? 'btn-danger' : 'btn-primary')
    + '" type="button" data-a="ok">' + cfg.ok + '</button></div>';
  let picked = cur;
  function close() { mask.remove(); document.removeEventListener('keydown', onKey); }
  function onKey(e) { if (e.key === 'Escape') close(); }
  box.querySelectorAll('.opt').forEach(b => b.addEventListener('click', () => {
    picked = Number(b.dataset.v);
    box.querySelectorAll('.opt').forEach(x => x.removeAttribute('data-on'));
    b.setAttribute('data-on', 'true');
  }));
  box.querySelectorAll('[data-a="x"]').forEach(b => b.addEventListener('click', close));
  box.querySelector('[data-a="ok"]').addEventListener('click', async () => {
    const btn = box.querySelector('[data-a="ok"]');
    btn.disabled = true;
    close();
    const payload = { kind: kind === 'power' ? 'wifi_power' : kind };
    if (kind === 'power') payload.value = picked;
    const r = await api('/api/router/action', payload).catch(() => null);
    if (!r) return errToast({ error: '请求没发出去' });
    if (!r.ok) return errToast(r);
    toast(cfg.t + '：' + (r.msg || '已发出'), '', cfg.i);
    if (kind === 'power') {
      const m = POWER_MODES.find(x => x[0] === picked);
      $('#qcPowerTxt').textContent = m[1].replace('模式', '');
      if (S.info && S.info.info) S.info.info.power_mode = picked;
    }
  });
  mask.addEventListener('click', e => { if (e.target === mask) close(); });
  document.addEventListener('keydown', onKey);
  mask.appendChild(box);
  document.body.appendChild(mask);
}

/* ==========================================================================
   IPv6 防火墙页
   ========================================================================== */
async function loadFirewall() {
  const [wl, ev] = await Promise.all([
    api('/api/router/whitelist').catch(() => ({ ok: false })),
    api('/api/events').catch(() => null),
  ]);
  S.wl = wl; if (ev) S.events = ev;
  renderFirewall(); renderEvents();
  renderCounts();
  loadInfo();
}
function renderFirewall() {
  const wl = S.wl;
  const badge = $('#fwBadge'), sw = $('#fwSw');
  if (!wl) {
    badge.className = 'badge badge-plain'; badge.innerHTML = '<span class="dot"></span>读取中';
    return;
  }
  if (!wl.ok) {
    badge.className = 'badge badge-err'; badge.innerHTML = '<span class="dot"></span>读不到';
    $('#ruleRows').innerHTML = '<tr><td colspan="7" class="sub">' + escHtml(wl.error || '读不到白名单') + '</td></tr>';
    return;
  }
  badge.className = 'badge ' + (wl.enabled ? 'badge-run' : 'badge-plain');
  badge.innerHTML = '<span class="dot"></span>' + (wl.enabled ? '已开启' : '已关闭');
  sw.dataset.on = wl.enabled ? 'true' : 'false';

  const st = (S.state && S.state.status) || {};
  const c = st.counters || {};
  const kv = [
    ['白名单规则', (wl.rules || []).length + ' 条'],
    ['上次同步', escHtml(ago(st.last_success_at))],
    ['累计写入', (st.total_writes || 0) + ' 次'],
    ['下次检测', (() => {
      if (!st.last_tick_at) return '—';
      const t = new Date(String(st.last_tick_at).replace(' ', 'T')).getTime();
      if (!t) return '—';
      const iv = pollInterval();
      const left = Math.ceil(iv - (Date.now() - t) / 1000);
      return left > 0 ? left + ' 秒后' : '马上开始下一轮';
    })()],
  ];
  $('#fwKv').innerHTML = kv.map(([k, v]) =>
    '<div class="kv"><div class="k">' + k + '</div><div class="v">' + v + '</div></div>').join('');

  /* 规则表 */
  const hosts = wl.hosts || [];
  const byMac = {};
  hosts.forEach(h => { byMac[String(h.mac || '').toUpperCase()] = h; });
  // 规则是否已在路由器上生效：与后端 trustlist.managed_pattern 一致，
  // 基础名、基础名@N、各自可再带 -端口。**按实读条目判**，不按设备在线 ——
  // 设备离线时条目仍保留在路由器上，照样是生效的；不绑定设备的规则（如 NAS）更没有「离线」一说。
  const escRe = s => String(s).replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const ownerOf = name => {
    if (!name) return '';
    return (wl.rules || []).some(r => r.name && new RegExp('^' + escRe(r.name) + '(@\\d+)?(-\\d+)?$')
      .test(String(name))) ? name : '';
  };
  // 规则在路由器上对应哪些条目（基础名 / 基础名@N / 各自可带 -端口）
  const entriesOf = name => (wl.entries || []).filter(e =>
    !!name && new RegExp('^' + escRe(name) + '(@\\d+)?(-\\d+)?$').test(String(e.Name || '')));
  const onRouter = name => entriesOf(name).length > 0;
  const tb = $('#ruleRows');
  tb.innerHTML = '';
  (wl.rules || []).forEach(r => {
    const h = byMac[String(r.mac || '').toUpperCase()];
    const tr = document.createElement('tr');
    const mine = entriesOf(r.name);
    const synced = mine.length > 0;
    const devOff = !synced && r.mac && h && !h.active;
    // 当前写进路由器的地址：去重后逐条显示，点击即复制
    const ips = [...new Set(mine.map(e => e.LocalIp || e.local_ip || '').filter(Boolean))];
    const addrCell = ips.length
      ? ips.map(ip => '<button class="v6" style="margin-bottom:3px" data-ip="' + escAttr(ip) + '"'
        + ' title="点击复制这条地址">' + svgI('copy') + '<span>' + escHtml(ip) + '</span></button>').join('')
      : '<span class="sub">还没写入</span>';
    tr.innerHTML = '<td><b style="font-weight:600">' + escHtml(r.name) + '</b></td>'
      + '<td>' + (h ? escHtml(h.name) + '<div class="mono" style="font-size:11px;color:var(--text-5)">'
        + escHtml(r.mac) + '</div>' : '<span class="sub">（不绑定设备）</span>') + '</td>'
      + '<td>' + addrCell + '</td>'
      + '<td>' + escHtml(String(r.port)) + '</td>'
      + '<td class="mono">' + escHtml(r.remote_ip) + '</td>'
      + '<td>' + (synced
        ? '<span class="badge badge-run"><span class="dot"></span>生效中</span>'
        : devOff
          ? '<span class="badge badge-warn">设备离线 · 待同步</span>'
          : '<span class="badge badge-plain">待同步</span>') + '</td>'
      + '<td><div class="acts"><button class="btn btn-sm" data-a="edit">' + svgI('edit') + '编辑</button>'
      + '<button class="btn btn-sm btn-danger" data-a="del">' + svgI('trash') + '</button></div></td>';
    tr.querySelectorAll('button[data-ip]').forEach(b => b.addEventListener('click', () => {
      const ip = b.dataset.ip;
      const old = b.innerHTML;
      if (copyText(ip)) {
        b.classList.add('copied');
        b.innerHTML = svgI('check') + '<span>已复制</span>';
        toast('已复制到剪贴板', ip, 'check');
        setTimeout(() => { b.classList.remove('copied'); b.innerHTML = old; }, 1400);
      } else toast('复制失败', '请手动选中复制', 'alert');
    }));
    tr.querySelector('[data-a="edit"]').addEventListener('click', () => ruleDialog(r));
    tr.querySelector('[data-a="del"]').addEventListener('click', () => removeRule(r));
    tb.appendChild(tr);
  });
  if (!(wl.rules || []).length) {
    tb.innerHTML = '<tr><td colspan="7" class="sub">还没有规则。点右上角「添加规则」选一台设备就能开始。</td></tr>';
  }

  /* 路由器上的条目 */
  const ent = $('#entRows');
  ent.innerHTML = '';
  (wl.entries || []).forEach(e => {
    const nm = e.Name || e.name || '—';
    const owned = ownerOf(nm);
    const tr = document.createElement('tr');
    tr.innerHTML = '<td class="mono" style="font-size:12px">' + escHtml(nm)
      + (owned ? '<span class="badge badge-accent" style="margin-left:6px">自动维护</span>'
        : '<span class="badge badge-plain" style="margin-left:6px">手工</span>') + '</td>'
      + '<td class="mono" style="font-size:11.5px">' + escHtml(e.LocalIp || e.local_ip || '—') + '</td>'
      + '<td>' + escHtml(String(e.Port == null || e.Port === '-1' ? '全部' : e.Port)) + '</td>'
      + '<td class="mono" style="font-size:11.5px">' + escHtml(e.RemoteIp || e.remote_ip || '::/0') + '</td>'
      + '<td><div class="acts">'
      + '<button class="btn btn-sm" data-a="edit">' + svgI('edit') + '编辑</button>'
      + '<button class="btn btn-sm btn-danger" data-a="del">' + svgI('trash') + '</button></div></td>';
    tr.querySelector('[data-a="edit"]').addEventListener('click', () => entryDialog(e, owned));
    tr.querySelector('[data-a="del"]').addEventListener('click', async () => {
      if (!confirm('从路由器白名单里删除这条条目？')) return;
      const r = await api('/api/router/whitelist/delete',
        { id: e.ID || e.id || '', name: nm }).catch(() => null);
      if (!r || !r.ok) return errToast(r);
      toast('条目已删除', '', 'check');
      loadFirewall();
    });
    ent.appendChild(tr);
  });
  $('#entHint').textContent = '上限 ' + (wl.max || 32) + ' 条 · 当前 '
    + (wl.entries || []).length + ' 条';
  if (!(wl.entries || []).length) {
    ent.innerHTML = '<tr><td colspan="5" class="sub">路由器白名单是空的</td></tr>';
  }
}
$('#fwSw').addEventListener('click', async () => {
  const sw = $('#fwSw');
  const want = sw.dataset.on !== 'true';
  sw.dataset.on = want ? 'true' : 'false';
  const r = await api('/api/router/firewall', { enable: want }).catch(() => null);
  if (!r || !r.ok) {
    sw.dataset.on = want ? 'false' : 'true';       // 回滚
    return errToast(r);
  }
  toast(want ? 'IPv6 防火墙已开启' : 'IPv6 防火墙已关闭',
    want ? '白名单生效中' : '白名单暂不生效，同步已暂停', want ? 'fw6' : 'alert');
  loadFirewall();
});
function renderEvents() {
  const ev = S.events;
  if (!ev) return;
  const q = ($('#evQ').value || '').trim().toLowerCase();
  const kind = $('#evKind').value || '';
  $('#evMax').innerHTML = [100, 200, 500, 1000, 2000, 5000].map(n =>
    '<option value="' + n + '"' + (n === (ev.max || 100) ? ' selected' : '') + '>' + n + '</option>').join('');
  const all = (ev.events || []).slice().reverse();
  const rows = all.filter(e => {
    if (kind && e.action !== kind) return false;
    if (!q) return true;
    return JSON.stringify(e).toLowerCase().includes(q);
  });
  $('#evCount').textContent = all.length;
  const tb = $('#evRows');
  tb.innerHTML = '';
  const LABEL = { created: '新增', updated: '更新', removed: '删除', fw: '开关' };
  rows.slice(0, 300).forEach(e => {
    const act = e.action || '';
    const cls = act === 'created' ? 'badge-run' : act === 'updated' ? 'badge-accent'
      : act === 'removed' ? 'badge-err' : 'badge-plain';
    const tr = document.createElement('tr');
    tr.innerHTML = '<td class="mono" style="font-size:11.5px">' + escHtml(e.ts || '') + '</td>'
      + '<td><span class="badge ' + cls + '">' + (LABEL[act] || escHtml(act)) + '</span></td>'
      + '<td>' + escHtml(e.device || '—') + '</td>'
      + '<td class="mono" style="font-size:11.5px">' + escHtml(e.addr || e.detail || '')
      + (e.port && e.port !== '全部' ? ' <span style="color:var(--text-5)">端口 ' + escHtml(e.port) + '</span>' : '')
      + '</td>';
    tb.appendChild(tr);
  });
  if (!rows.length) tb.innerHTML = '<tr><td colspan="4" class="sub">还没有记录</td></tr>';
}
$('#evQ').addEventListener('input', renderEvents);
$('#evKind').addEventListener('change', renderEvents);
$('#evMax').addEventListener('change', async e => {
  const r = await api('/api/events/max', { max: Number(e.target.value) }).catch(() => null);
  if (!r || !r.ok) return errToast(r);
  S.events.max = Number(e.target.value);
  toast('保留上限已改为 ' + e.target.value + ' 条', '', 'check');
});
$('#btnEvClear').addEventListener('click', async () => {
  if (!confirm('清空同步记录？只清历史，不影响白名单和同步。')) return;
  const r = await api('/api/events/clear', {}).catch(() => null);
  if (!r || !r.ok) return errToast(r);
  toast('同步记录已清空', '', 'trash');
  loadFirewall();
});
$('#btnSyncNow').addEventListener('click', async () => {
  const btn = $('#btnSyncNow');
  btn.disabled = true;
  toast('正在同步', '马上就好', 'refresh');
  const r = await api('/api/sync', {}).catch(() => null);
  btn.disabled = false;
  if (!r) return errToast({ error: '请求没发出去' });
  if (r.ok) toast('同步完成', '', 'check'); else errToast(r);
  await refreshState();
  loadFirewall();
});

/* 规则弹窗 */
function ruleDialog(src) {
  const isNew = !src;
  const hosts = (S.wl && S.wl.hosts) || [];
  const mask = el('div', 'tpick-mask');
  const box = el('div', 'epick');
  const cur = src || { name: '', mac: '', port: '-1', remote_ip: '::/0' };
  box.innerHTML = '<div class="th">' + svgI('fw6')
    + '<span>' + (isNew ? '添加规则' : '编辑规则') + '</span>'
    + '<button class="btn btn-sm" type="button" data-a="x">关闭</button></div>'
    + '<div class="ebody">'
    + '<div class="efld"><label>设备<em>*</em></label>'
    + '<select class="sel" id="rDev">' + hosts.map(h =>
      '<option value="' + escAttr(h.mac) + '"' + (String(h.mac).toUpperCase() === String(cur.mac).toUpperCase() ? ' selected' : '')
      + '>' + escHtml((h.name || '未知') + ' · ' + h.mac + (h.active ? '' : '（离线）')) + '</option>').join('')
    + '</select><div class="hp">放行哪台设备；规则会跟着这台设备的地址变化自动更新</div></div>'
    + '<div class="egrid2">'
    + '<div class="efld"><label>服务名称<em>*</em></label>'
    + '<input class="inp" id="rName" value="' + escAttr(cur.name) + '" placeholder="例如 NAS"></div>'
    + '<div class="efld"><label>放行端口</label>'
    + '<input class="inp" id="rPort" value="' + escAttr(cur.port) + '" placeholder="-1 表示全部端口"></div>'
    + '</div>'
    + '<div class="efld"><label>允许来源</label>'
    + '<input class="inp" id="rRemote" value="' + escAttr(cur.remote_ip) + '" placeholder="::/0 表示不限制">'
    + '<div class="hp">多个端口用英文逗号分隔，如 443,6690</div></div>'
    + '</div><div class="efoot">'
    + '<button class="btn" type="button" data-a="x">取消</button>'
    + '<button class="btn btn-primary" type="button" data-a="save">'
    + (isNew ? '添加并同步' : '保存修改') + '</button></div>';
  const devSel = box.querySelector('#rDev');
  const nameInp = box.querySelector('#rName');
  devSel.addEventListener('change', () => {
    const h = hosts.find(x => x.mac === devSel.value);
    if (h && !nameInp.value.trim()) nameInp.value = h.name || '';
  });
  if (isNew && hosts.length && !nameInp.value) nameInp.value = hosts[0].name || '';
  function close() { mask.remove(); document.removeEventListener('keydown', onKey); }
  function onKey(e) { if (e.key === 'Escape') close(); }
  box.querySelectorAll('[data-a="x"]').forEach(b => b.addEventListener('click', close));
  box.querySelector('[data-a="save"]').addEventListener('click', async () => {
    const payload = {
      action: isNew ? 'add' : 'update',
      name: nameInp.value.trim(),
      mac: devSel.value,
      port: box.querySelector('#rPort').value.trim() || '-1',
      remote_ip: box.querySelector('#rRemote').value.trim() || '::/0',
    };
    if (!isNew) payload.old_name = cur.name;
    if (!payload.name) { nameInp.classList.add('miss'); return toast('请填服务名称', '', 'alert'); }
    const r = await api('/api/rules', payload).catch(() => null);
    if (!r || !r.ok) return errToast(r);
    close();
    toast(isNew ? '规则已添加' : '规则已更新', '已立即同步一轮', 'check');
    loadFirewall();
  });
  if (!hosts.length) {
    box.querySelector('[data-a="save"]').disabled = true;
    devSel.innerHTML = '<option>（先让路由器认识设备）</option>';
  }
  mask.addEventListener('click', e => { if (e.target === mask) close(); });
  document.addEventListener('keydown', onKey);
  mask.appendChild(box);
  document.body.appendChild(mask);
}
/* 路由器手工条目的编辑弹窗（改版时丢掉的功能；走 /api/router/whitelist/update）。
   owned 非空说明这条归某条规则自动维护，改它会被下一轮同步覆盖 —— 弹窗里说清楚。 */
function entryDialog(e, owned) {
  const mask = el('div', 'tpick-mask');
  const box = el('div', 'epick');
  const port = String(e.Port == null ? '-1' : e.Port);
  box.innerHTML = '<div class="th">' + svgI('link')
    + '<span>编辑白名单条目</span>'
    + '<button class="btn btn-sm" type="button" data-a="x">关闭</button></div>'
    + '<div class="ebody">'
    + (owned ? '<div class="hp" style="margin-bottom:10px">这条由规则自动维护，'
      + '手工改完可能马上被下一次同步改回去；要长期生效请改成不重名的条目，或去编辑那条规则。</div>' : '')
    + '<div class="efld"><label>服务名称<em>*</em></label>'
    + '<input class="inp" id="eName" value="' + escAttr(e.Name || e.name || '') + '"></div>'
    + '<div class="efld"><label>本机 / 地址<em>*</em></label>'
    + '<input class="inp mono" id="eLocal" value="' + escAttr(e.LocalIp || e.local_ip || '') + '">'
    + '<div class="hp">对外的 IPv6 地址</div></div>'
    + '<div class="egrid2">'
    + '<div class="efld"><label>放行端口</label>'
    + '<input class="inp" id="ePort" value="' + escAttr(port) + '" placeholder="-1 表示全部端口"></div>'
    + '<div class="efld"><label>允许来源</label>'
    + '<input class="inp" id="eRemote" value="' + escAttr(e.RemoteIp || e.remote_ip || '::/0') + '"></div>'
    + '</div></div><div class="efoot">'
    + '<button class="btn" type="button" data-a="x">取消</button>'
    + '<button class="btn btn-primary" type="button" data-a="save">保存修改</button></div>';
  function close() { mask.remove(); document.removeEventListener('keydown', onKey); }
  function onKey(ev) { if (ev.key === 'Escape') close(); }
  box.querySelectorAll('[data-a="x"]').forEach(b => b.addEventListener('click', close));
  box.querySelector('[data-a="save"]').addEventListener('click', async () => {
    const payload = {
      id: e.ID || e.id || '',
      name: box.querySelector('#eName').value.trim(),
      local_ip: box.querySelector('#eLocal').value.trim(),
      port: box.querySelector('#ePort').value.trim() || '-1',
      remote_ip: box.querySelector('#eRemote').value.trim() || '::/0',
    };
    const r = await api('/api/router/whitelist/update', payload).catch(() => null);
    if (!r || !r.ok) return errToast(r);   // 校验文案由后端给，界面不显示内部参数
    close();
    toast('条目已更新', '', 'check');
    loadFirewall();
  });
  mask.addEventListener('click', ev => { if (ev.target === mask) close(); });
  document.addEventListener('keydown', onKey);
  mask.appendChild(box);
  document.body.appendChild(mask);
}
async function removeRule(r) {
  if (!confirm('删除规则「' + r.name + '」？它名下本程序维护的白名单条目会一起从路由器删掉。')) return;
  const res = await api('/api/rules', { action: 'remove', name: r.name }).catch(() => null);
  if (!res || !res.ok) return errToast(res);
  toast('规则已删除', '', 'trash');
  loadFirewall();
}
$('#btnAddRule').addEventListener('click', () => {
  if (!S.wl || !S.wl.ok) return toast('还读不到设备列表', '先让它连上路由器', 'alert');
  ruleDialog(null);
});
$('#btnRefreshFw').addEventListener('click', loadFirewall);
$('#btnRefreshDev').addEventListener('click', () => { loadInfo(); loadHosts(); });

/* ==========================================================================
   计划任务
   ========================================================================== */
async function loadTasks() {
  S.tasks = await api('/api/tasks').catch(() => null);
  renderTasks();
  renderCounts();
}
const WEEK = ['一', '二', '三', '四', '五', '六', '日'];
function renderTasks() {
  const t = S.tasks;
  if (!t) return;
  const tasks = t.tasks || [];
  const on = tasks.filter(x => x.enabled).length;
  const next = tasks.filter(x => x.enabled && x.next_at)
    .sort((a, b) => (a.next_at < b.next_at ? -1 : 1))[0];
  $('#taskSub').textContent = tasks.length + ' 个任务 · ' + on + ' 个启用'
    + (next ? ' · 下次执行 ' + next.next_at + ' ' + next.name : '');
  $('#taskTz').textContent = '按容器本地时间 ' + (t.tz || '') + (t.utc ? ' · 容器是 UTC，注意和本地时差' : '');
  const tb = $('#taskRows');
  tb.innerHTML = '';
  tasks.forEach(x => {
    const tr = document.createElement('tr');
    let res;
    const brief = m => {
      const t = String(m || '').replace(/\s+/g, ' ').trim();
      return escHtml(t.length > 22 ? t.slice(0, 22) + '…' : t);
    };
    if (x.running) res = '<span class="badge badge-accent">执行中…</span>';
    else if (x.last_ok === true) res = '<span class="badge badge-run" title="' + escAttr(x.last_msg || '') + '">' + brief(x.last_msg || '成功') + '</span>';
    else if (x.last_ok === false) res = '<span class="badge badge-err" title="' + escAttr(x.last_msg || '') + '">' + brief(x.last_msg || '失败') + '</span>';
    else if (x.last_msg) res = '<span class="badge badge-warn" title="' + escAttr(x.last_msg) + '">' + brief(x.last_msg) + '</span>';
    else res = '<span class="sub">还没执行过</span>';
    tr.innerHTML = '<td><b style="font-weight:600">' + escHtml(x.name) + '</b></td>'
      + '<td>' + escHtml(x.kind_label || x.kind) + '</td>'
      + '<td>' + escHtml(x.when || '') + '</td>'
      + '<td class="mono" style="font-size:11.5px;color:var(--text-3)">' + escHtml(x.next_at || '—') + '</td>'
      + '<td>' + res + '</td>'
      + '<td><button class="sw" data-on="' + (x.enabled ? 'true' : 'false') + '"></button></td>'
      + '<td><div class="acts"><button class="btn btn-sm" data-a="run">立即执行</button>'
      + '<button class="btn btn-sm" data-a="edit">' + svgI('edit') + '</button>'
      + '<button class="btn btn-sm btn-danger" data-a="del">' + svgI('trash') + '</button></div></td>';
    tr.querySelector('.sw').addEventListener('click', async () => {
      const want = tr.querySelector('.sw').dataset.on !== 'true';
      const r = await api('/api/tasks/toggle', { id: x.id, enabled: want }).catch(() => null);
      if (!r || !r.ok) return errToast(r);
      toast(want ? '任务已启用' : '任务已停用', x.name, want ? 'check' : 'clock');
      loadTasks();
    });
    tr.querySelector('[data-a="run"]').addEventListener('click', async () => {
      const r = await api('/api/tasks/run', { id: x.id }).catch(() => null);
      if (!r) return errToast({ error: '请求没发出去' });
      if (r.ok) toast('已执行：' + x.name, r.msg || '', 'zap'); else errToast(r);
      setTimeout(loadTasks, 800);
    });
    tr.querySelector('[data-a="edit"]').addEventListener('click', () => taskDialog(x));
    tr.querySelector('[data-a="del"]').addEventListener('click', async () => {
      if (!confirm('删除任务「' + x.name + '」？')) return;
      const r = await api('/api/tasks/delete', { id: x.id }).catch(() => null);
      if (!r || !r.ok) return errToast(r);
      toast('任务已删除', x.name, 'trash');
      loadTasks();
    });
    tb.appendChild(tr);
  });
  if (!tasks.length) {
    tb.innerHTML = '<tr><td colspan="7" class="sub">还没有计划任务。点右上角「添加任务」。</td></tr>';
  }
}
function taskDialog(src) {
  const isNew = !src;
  const t = S.tasks || {};
  const kinds = t.kinds || {};
  const pms = t.power_modes || {};
  const cur = src || { kind: 'reboot', at: '03:30', days: [1, 2, 3, 4, 5, 6, 7], enabled: true, params: {} };
  const mask = el('div', 'tpick-mask');
  const box = el('div', 'epick');
  box.innerHTML = '<div class="th">' + svgI('cal') + '<span>' + (isNew ? '添加任务' : '编辑任务')
    + '</span><button class="btn btn-sm" type="button" data-a="x">关闭</button></div>'
    + '<div class="ebody">'
    + '<div class="egrid2">'
    + '<div class="efld"><label>任务名称</label><input class="inp" id="tName" value="'
    + escAttr(cur.name || '') + '" placeholder="留空用类型名"></div>'
    + '<div class="efld"><label>类型</label><select class="sel" id="tKind">'
    + Object.entries(kinds).map(([k, v]) => '<option value="' + k + '"'
      + (k === cur.kind ? ' selected' : '') + '>' + escHtml(v) + '</option>').join('')
    + '</select></div></div>'
    + '<div class="egrid2">'
    + '<div class="efld"><label>执行时间</label><input class="inp" type="time" id="tAt" value="'
    + escAttr(cur.at || '03:30') + '"></div>'
    + '<div class="efld"><label>重复</label><select class="sel" id="tDays">'
    + '<option value="all">每天</option><option value="wd">周一至周五</option>'
    + '<option value="custom">自定义…</option></select></div></div>'
    + '<div class="efld hide" id="tDaysBox"><label>选择星期</label><div class="wdays" id="tDaysPick">'
    + WEEK.map((w, i) => '<button class="wday" type="button" data-d="' + (i + 1) + '">' + w + '</button>').join('')
    + '</div></div>'
    + '<div class="efld hide" id="tPowBox"><label>功率模式</label><select class="sel" id="tPow">'
    + Object.entries(pms).map(([k, v]) => '<option value="' + k + '"'
      + (String(k) === String((cur.params || {}).power_mode) ? ' selected' : '') + '>' + escHtml(v) + '</option>').join('')
    + '</select></div>'
    + '<div class="efld hide" id="tDevBox"><label>唤醒哪几台设备<em>*</em></label>'
    + '<div class="hp" style="margin:0 0 8px">从设备列表里选，最多 20 台；多台之间会自动间隔一秒发。</div>'
    + '<div class="devpick" id="tDevPick"></div></div>'
    + '</div><div class="efoot">'
    + '<button class="btn" type="button" data-a="x">取消</button>'
    + '<button class="btn btn-primary" type="button" data-a="save">'
    + (isNew ? '添加任务' : '保存修改') + '</button></div>';

  const kindSel = box.querySelector('#tKind');
  const daysSel = box.querySelector('#tDays');
  const powBox = box.querySelector('#tPowBox');
  const devBox = box.querySelector('#tDevBox');
  const daysBox = box.querySelector('#tDaysBox');
  const pick = box.querySelector('#tDaysPick');
  const chosen = new Set(cur.days && cur.days.length ? cur.days : [1, 2, 3, 4, 5, 6, 7]);

  function syncDaysUi() {
    const d = chosen.size === 7 ? 'all' : ([...chosen].sort().join(',') === '1,2,3,4,5' ? 'wd' : 'custom');
    daysSel.value = d;
    daysBox.classList.toggle('hide', d !== 'custom');
    pick.querySelectorAll('.wday').forEach(b => {
      b.dataset.on = chosen.has(Number(b.dataset.d)) ? 'true' : 'false';
    });
  }
  pick.querySelectorAll('.wday').forEach(b => b.addEventListener('click', () => {
    const d = Number(b.dataset.d);
    if (chosen.has(d)) chosen.delete(d); else chosen.add(d);
    syncDaysUi();
  }));
  daysSel.addEventListener('change', () => {
    if (daysSel.value === 'all') { chosen.clear(); [1, 2, 3, 4, 5, 6, 7].forEach(x => chosen.add(x)); }
    else if (daysSel.value === 'wd') { chosen.clear(); [1, 2, 3, 4, 5].forEach(x => chosen.add(x)); }
    syncDaysUi();
  });
  function syncKindUi() {
    powBox.classList.toggle('hide', kindSel.value !== 'wifi_power');
    devBox.classList.toggle('hide', kindSel.value !== 'wake');
    if (kindSel.value === 'wake') buildDevPick();
  }
  let pickedDevs = null;
  function buildDevPick() {
    if (pickedDevs) return;
    const box2 = box.querySelector('#tDevPick');
    const hosts = (S.hosts && S.hosts.hosts) || [];
    if (!hosts.length) {
      box2.innerHTML = '<div class="sub">读不到设备列表，先到「设备」页刷新一下</div>';
      pickedDevs = new Set();
      return;
    }
    const preset = ((cur.params || {}).devices || []).map(d => String(d.mac || '').toUpperCase());
    pickedDevs = new Set(preset);
    box2.innerHTML = hosts.map(h => {
      const on = pickedDevs.has(String(h.mac).toUpperCase());
      return '<button class="devchip" type="button" data-mac="' + escAttr(h.mac) + '"'
        + (on ? ' data-on="true"' : '') + (h.active ? '' : ' data-off="true"') + '>'
        + '<span class="nm">' + escHtml(h.name || h.mac) + '</span>'
        + '<span class="mc">' + escHtml(h.mac) + '</span></button>';
    }).join('');
    box2.querySelectorAll('.devchip').forEach(b => b.addEventListener('click', () => {
      const m = String(b.dataset.mac).toUpperCase();
      if (pickedDevs.has(m)) { pickedDevs.delete(m); b.removeAttribute('data-on'); }
      else {
        if (pickedDevs.size >= 20) return toast('最多选 20 台', '', 'alert');
        pickedDevs.add(m); b.dataset.on = 'true';
      }
    }));
  }
  kindSel.addEventListener('change', syncKindUi);
  syncDaysUi(); syncKindUi();

  function close() { mask.remove(); document.removeEventListener('keydown', onKey); }
  function onKey(e) { if (e.key === 'Escape') close(); }
  box.querySelectorAll('[data-a="x"]').forEach(b => b.addEventListener('click', close));
  box.querySelector('[data-a="save"]').addEventListener('click', async () => {
    const kind = kindSel.value;
    const payload = {
      id: cur.id || '',
      name: box.querySelector('#tName').value.trim(),
      kind: kind,
      at: box.querySelector('#tAt').value || '03:30',
      days: [...chosen].sort(),
      enabled: isNew ? true : !!cur.enabled,
      params: {},
    };
    if (kind === 'wifi_power') payload.params.power_mode = Number(box.querySelector('#tPow').value);
    if (kind === 'wake') {
      const hosts = (S.hosts && S.hosts.hosts) || [];
      const sel = [...(pickedDevs || new Set())];
      if (!sel.length) return toast('至少选一台设备', '', 'alert');
      payload.params.devices = sel.map(m => {
        const h = hosts.find(x => String(x.mac).toUpperCase() === m) || {};
        return { mac: m, name: h.name || '', ipv4: h.ipv4 || '' };
      });
    }
    if (!payload.days.length) return toast('至少选一天', '', 'alert');
    const r = await api('/api/tasks/save', payload).catch(() => null);
    if (!r || !r.ok) return errToast(r);
    close();
    toast(isNew ? '任务已添加' : '任务已保存', payload.at + ' · ' + (chosen.size === 7 ? '每天' : chosen.size + ' 天'),
      'check');
    loadTasks();
  });
  mask.addEventListener('click', e => { if (e.target === mask) close(); });
  document.addEventListener('keydown', onKey);
  mask.appendChild(box);
  document.body.appendChild(mask);
}
$('#btnAddTask').addEventListener('click', () => taskDialog(null));

/* ==========================================================================
   通知
   ========================================================================== */
async function loadNotify() {
  S.notify = await api('/api/notify').catch(() => null);
  renderNotify(); renderCounts();
  if (S.page === 'notify' && S.nTab === 'history') loadHistory();
}
async function loadHistory() {
  S.hist = await api('/api/notify/history').catch(() => null);
  renderHistory();
}
function chPreset(t) {
  const p = ((S.notify && S.notify.presets) || []).find(x => x.t === t);
  return p || { t: t, l: t, d: '', f: [] };
}
function chSummary(c) {
  const v = c.config || {};
  const tail = s => s && s.length > 10 ? String(s).slice(0, 4) + '…' + String(s).slice(-4) : (s || '—');
  switch (c.type) {
    case 'ntfy': return 'ntfy · ' + String(v.server || 'https://ntfy.sh').replace(/^https?:\/\//, '') + '/' + (v.topic || '—');
    case 'gotify': return 'Gotify · ' + String(v.server || '—').replace(/^https?:\/\//, '');
    case 'bark': return 'Bark · ' + String(v.server || 'api.day.app').replace(/^https?:\/\//, '');
    case 'telegram': return 'Telegram · ' + (v.chatId || '—');
    case 'smtp': return '邮件 · ' + (v.to ? String(v.to).split(',').filter(x => x.trim()).length + ' 个收件人' : '—');
    case 'webhook': return 'Webhook · ' + String(v.url || '—').replace(/^https?:\/\//, '').slice(0, 44);
    case 'wecom': return '企业微信 · key ' + tail(v.key);
    case 'dingtalk': return '钉钉 · ' + tail(v.token);
    case 'feishu': return '飞书 · ' + tail(v.token);
    case 'serverchan': return 'Server 酱 · ' + tail(v.sendkey);
    case 'pushplus': return 'PushPlus · ' + tail(v.token);
  }
  return chPreset(c.type).l;
}
function renderNotify() {
  const n = S.notify;
  if (!n) return;
  const chans = n.channels || [];
  const evs = n.events || [];
  const onCh = chans.filter(c => c.enabled).length;
  const onEv = evs.filter(e => e.on).length;
  $('#nSub').textContent = onCh + ' / ' + chans.length + ' 个渠道已启用 · '
    + evs.length + ' 个事件中开启 ' + onEv + ' 个 · 标题由事件自动生成';
  $('#chanHint').textContent = onCh + ' / ' + chans.length + ' 已启用';
  const seg = $('#nSeg');
  seg.querySelector('[data-t="channels"]').textContent = '渠道 ' + chans.length;
  seg.querySelector('[data-t="events"]').textContent = '事件订阅 ' + evs.length;

  /* 渠道列表 */
  const box = $('#chanRows');
  box.innerHTML = '';
  if (!chans.length) {
    box.innerHTML = '<div class="cb sub" style="padding:22px 14px">还没有通知渠道，点右上角「添加渠道」加一个</div>';
  }
  chans.forEach(c => {
    const row = el('div', 'chanrow');
    row.innerHTML = '<button class="sw" data-on="' + (c.enabled ? 'true' : 'false') + '"></button>'
      + '<div class="cinfo"><div class="cn">' + escHtml(c.name) + '</div>'
      + '<div class="cs">' + escHtml(chSummary(c)) + '</div></div>'
      + '<div class="cacts">'
      + '<button class="btn btn-sm" data-a="test">' + svgI('send') + '测试</button>'
      + '<button class="btn btn-sm" data-a="edit">编辑</button>'
      + '<button class="btn btn-sm btn-danger" data-a="del" title="删除">' + svgI('trash') + '</button></div>';
    row.querySelector('.sw').addEventListener('click', async () => {
      const want = c.enabled ? false : true;
      const next = chans.map(x => x.id === c.id ? Object.assign({}, x, { enabled: want }) : x);
      const r = await saveChannels(next).catch(() => null);
      if (!r) return errToast({ error: '请求没发出去' });
      toast(want ? '渠道已启用' : '渠道已停用', c.name, want ? 'check' : 'clock');
    });
    row.querySelector('[data-a="test"]').addEventListener('click', async e => {
      const b = e.currentTarget;
      b.disabled = true;
      const r = await api('/api/notify/channel/test', { channel: c }).catch(() => null);
      b.disabled = false;
      if (r && r.ok) toast('测试消息已发出', c.name + ' · 收到就说明通了', 'send');
      else errToast(r);
    });
    row.querySelector('[data-a="edit"]').addEventListener('click', () => channelEditor(c));
    row.querySelector('[data-a="del"]').addEventListener('click', async () => {
      if (!confirm('删除渠道「' + c.name + '」？')) return;
      const next = chans.filter(x => x.id !== c.id);
      const r = await saveChannels(next).catch(() => null);
      if (!r) return errToast({ error: '请求没发出去' });
      toast('渠道已删除', c.name, 'trash');
    });
    box.appendChild(row);
  });

  /* 投递策略 */
  $('#polEnabled').dataset.on = n.enabled ? 'true' : 'false';
  const q = parseQuiet(n.quiet);
  $('#polQuietSw').dataset.on = q ? 'true' : 'false';
  $('#polQuietFrom').value = q ? q[0] : '23:00';
  $('#polQuietTo').value = q ? q[1] : '07:00';
  $('#polQuietFrom').disabled = $('#polQuietTo').disabled = !q;
  $('#polDedupe').value = Math.round((n.dedupe || 300) / 60);
  $('#polHist').innerHTML = (n.history_choices || [50, 100, 150, 200]).map(v =>
    '<option value="' + v + '"' + (v === n.history_max ? ' selected' : '') + '>' + v
    + ' 条' + (v === 50 ? '（默认）' : v === 200 ? '（上限）' : '') + '</option>').join('');

  /* 事件订阅 */
  const groups = {};
  evs.forEach(e => { (groups[e.group] = groups[e.group] || []).push(e); });
  const gid = { 'IPv6 防火墙': 'fw', '设备': 'dev', '计划任务': 'task', '系统': 'sys' };
  Object.entries(gid).forEach(([name, id]) => {
    const list = groups[name] || [];
    const holder = document.getElementById('evg-' + id);
    if (!holder) return;
    holder.innerHTML = '';
    list.forEach((e, i) => {
      const row = el('div', '');
      row.style.cssText = 'display:flex;flex-wrap:wrap;align-items:flex-start;gap:12px;'
        + 'border-bottom:1px solid var(--line-row);padding:10px 14px';
      if (i === list.length - 1) row.style.borderBottom = '0';
      row.innerHTML = '<button class="sw" data-on="' + (e.on ? 'true' : 'false') + '" style="margin-top:2px"></button>'
        + '<div style="min-width:220px;flex:1">'
        + '<div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">'
        + '<span style="font-size:12.5px;font-weight:500">' + escHtml(e.title) + '</span>'
        + '<span class="badge ' + (e.level === 'urgent' ? 'badge-err' : 'badge-plain') + '">'
        + (e.level === 'urgent' ? '紧急' : '普通') + '</span></div>'
        + '<div style="margin-top:2px;font-size:11px;color:var(--text-5)">'
        + (e.level === 'urgent' ? '静默时段也会照常发送' : '静默时段内不发送') + '</div>'
        + '</div>';
      row.querySelector('.sw').addEventListener('click', async ev => {
        const sw = ev.currentTarget;
        const want = sw.dataset.on !== 'true';
        sw.dataset.on = want ? 'true' : 'false';
        const map = {};
        evs.forEach(x => { map[x.code] = x.code === e.code ? want : x.on; });
        const r = await api('/api/notify/policy', { events: map }).catch(() => null);
        if (!r || !r.ok) {
          sw.dataset.on = want ? 'false' : 'true';
          return errToast(r);
        }
        S.notify = r;
        renderNotify();
      });
      holder.appendChild(row);
    });
    const hint = document.querySelector('.hint[data-g="' + id + '"]');
    if (hint) hint.textContent = list.filter(x => x.on).length + ' / ' + list.length + ' 已开启';
  });
  renderHistory();
}
function parseQuiet(s) {
  const m = String(s || '').match(/^(\d{1,2}:\d{2})-(\d{1,2}:\d{2})$/);
  if (!m) return null;
  const fix = x => (x.length === 4 ? '0' + x : x);
  return [fix(m[1]), fix(m[2])];
}
async function saveChannels(list) {
  const r = await api('/api/notify/channels', { channels: list });
  if (!r || !r.ok) { errToast(r); throw new Error('save failed'); }
  S.notify.channels = r.channels || list;
  renderNotify(); renderCounts();
  return r;
}
function renderHistory() {
  const h = S.hist;
  const tb = $('#histRows');
  if (!h) { tb.innerHTML = '<tr><td colspan="5" class="sub">正在读取…</td></tr>'; return; }
  const items = (h.items || []).slice().reverse();
  $('#histHint').textContent = '最近 ' + (h.max || 50) + ' 条 · 上限 ' + (h.limit || 200) + ' 条';
  tb.innerHTML = '';
  items.forEach(x => {
    const bad = !x.ok;
    const tr = document.createElement('tr');
    tr.innerHTML = '<td class="mono" style="font-size:11.5px">' + escHtml(x.ts || '') + '</td>'
      + '<td style="font-size:12px;color:var(--text-3)">' + escHtml(x.channel || '') + '</td>'
      + '<td><span class="badge ' + (x.level === 'urgent' ? 'badge-err' : 'badge-accent') + '">'
      + escHtml(x.title || '') + '</span></td>'
      + '<td><span class="badge ' + (bad ? 'badge-err' : 'badge-run') + '">'
      + (bad ? '失败' : '成功') + '</span>'
      + (bad && x.error ? '<div style="font-size:10.5px;color:var(--err-text);margin-top:3px">'
        + escHtml(String(x.error).slice(0, 60)) + '</div>' : '') + '</td>'
      + '<td style="font-size:12px;color:var(--text-2)">' + escHtml(String(x.text || '').replace(/\n/g, ' ').slice(0, 120)) + '</td>';
    tb.appendChild(tr);
  });
  if (!items.length) tb.innerHTML = '<tr><td colspan="5" class="sub">还没有推送记录</td></tr>';
}

/* 渠道编辑弹窗：字段定义全部来自后端预设，前端不写死任何一种渠道 */
function channelEditor(src) {
  const isNew = !src;
  const ch = isNew
    ? { id: '', t: 'wecom', type: 'wecom', name: '', enabled: true, config: {} }
    : { id: src.id, t: src.type, type: src.type, name: src.name,
        enabled: !!src.enabled, config: Object.assign({}, src.config) };
  const mask = el('div', 'tpick-mask');
  const box = el('div', 'epick');
  document.body.appendChild(mask);
  mask.appendChild(box);
  box.innerHTML = '<div class="th">' + svgI('bell')
    + '<span>' + (isNew ? '添加通知渠道' : '编辑渠道') + '</span>'
    + '<button class="btn btn-sm" type="button" data-a="x">关闭</button></div>'
    + '<div class="ebody">'
    + '<div class="egrid2">'
    + '<div class="efld"><label>渠道名称</label>'
    + '<input class="inp" id="ecName" placeholder="例如：家庭群通知" value="' + escAttr(ch.name) + '"></div>'
    + '<div class="efld"><label>类型</label><select class="sel" id="ecType"' + (isNew ? '' : ' disabled')
    + '>' + ((S.notify.presets) || []).map(p => '<option value="' + p.t + '"'
      + (p.t === ch.t ? ' selected' : '') + '>' + escHtml(p.l) + '</option>').join('')
    + '</select></div></div>'
    + '<div class="desc" id="ecDesc"></div>'
    + '<div id="ecFields" style="display:flex;flex-direction:column;gap:12px"></div>'
    + '<label class="eon"><button class="sw" type="button" data-a="on" data-on="'
    + (ch.enabled ? 'true' : 'false') + '"></button>启用这个渠道</label>'
    + '</div><div class="efoot">'
    + '<button class="btn" type="button" data-a="test">' + svgI('send') + '测试这条</button>'
    + '<span style="flex:1"></span>'
    + '<button class="btn" type="button" data-a="x">取消</button>'
    + '<button class="btn btn-primary" type="button" data-a="save">'
    + (isNew ? '创建渠道' : '保存修改') + '</button></div>';
  const fbox = box.querySelector('#ecFields');
  const desc = box.querySelector('#ecDesc');

  function syncCfg() {
    const nm = box.querySelector('#ecName');
    if (nm) ch.name = nm.value;
    chPreset(ch.t).f.forEach(f => {
      const n = box.querySelector('#ec-' + f.k);
      if (n) ch.config[f.k] = n.value;
    });
  }
  function fieldHtml(f) {
    const v = ch.config[f.k] == null ? '' : String(ch.config[f.k]);
    const ctl = f.ty === 'area'
      ? '<textarea class="area" id="ec-' + f.k + '" placeholder="' + escAttr(f.ph || '') + '">'
        + escHtml(v) + '</textarea>'
      : '<input class="inp" id="ec-' + f.k + '" type="' + (f.ty === 'password' ? 'password' : 'text')
      + '" value="' + escAttr(v) + '" placeholder="' + escAttr(f.ph || '') + '">';
    return '<div class="efld"><label>' + escHtml(f.l) + (f.p ? '<em>*</em>' : '') + '</label>' + ctl
      + (f.hp ? '<div class="hp">' + escHtml(f.hp) + '</div>' : '') + '</div>';
  }
  function renderFields() {
    const p = chPreset(ch.t);
    desc.textContent = p.d || '';
    let html = '', buf = [];
    const flush = () => {
      if (!buf.length) return;
      html += '<div class="egrid2">' + buf.join('') + '</div>';
      buf = [];
    };
    p.f.forEach(f => {
      const one = fieldHtml(f);
      if (f.half) { buf.push(one); if (buf.length === 2) flush(); }
      else { flush(); html += one; }
    });
    flush();
    fbox.innerHTML = html;
  }
  function collect() {
    syncCfg();
    const cfg = {};
    Object.keys(ch.config).forEach(k => {
      const v = String(ch.config[k] == null ? '' : ch.config[k]).trim();
      if (v) cfg[k] = v;
    });
    return { id: ch.id, type: ch.t, name: String(ch.name || '').trim(), enabled: ch.enabled, config: cfg };
  }
  function close() { mask.remove(); document.removeEventListener('keydown', onKey); }
  function onKey(e) { if (e.key === 'Escape') close(); }
  box.querySelector('#ecType').addEventListener('change', e => {
    syncCfg();
    ch.t = e.target.value;
    ch.config = {};                    /* 换了类型，旧字段没意义 */
    renderFields();
  });
  box.querySelector('[data-a="on"]').addEventListener('click', e => {
    ch.enabled = !ch.enabled;
    e.currentTarget.dataset.on = ch.enabled ? 'true' : 'false';
  });
  box.querySelectorAll('[data-a="x"]').forEach(b => b.addEventListener('click', close));
  box.querySelector('[data-a="test"]').addEventListener('click', async e => {
    const b = e.currentTarget;
    b.disabled = true;
    const r = await api('/api/notify/channel/test', { channel: collect() }).catch(() => null);
    b.disabled = false;
    if (r && r.ok) toast('测试消息已发出', '收到就说明这条配好了', 'send');
    else errToast(r);
  });
  box.querySelector('[data-a="save"]').addEventListener('click', async () => {
    const one = collect();
    if (!one.name) {
      box.querySelector('#ecName').focus();
      return toast('请先填渠道名称', '名字是给你自己看的，比如「家庭群」', 'alert');
    }
    const miss = [];
    chPreset(ch.t).f.forEach(f => {
      const node = box.querySelector('#ec-' + f.k);
      const v = String((one.config[f.k] == null ? '' : one.config[f.k])).trim();
      if (f.p && !v) { miss.push(f.l); if (node) node.classList.add('miss'); }
      else if (node) node.classList.remove('miss');
    });
    if (miss.length) return toast('还有必填项没填', miss.join('、'), 'alert');
    const list = (S.notify.channels || []).slice();
    const i = list.findIndex(x => x.id === one.id);
    if (i >= 0) list[i] = one; else { one.id = one.id || ('c' + Date.now().toString(36)); list.push(one); }
    try { await saveChannels(list); } catch (e) { return; }
    close();
    toast(isNew ? '渠道已创建' : '渠道已更新', one.name + ' · ' + chPreset(ch.t).l, 'check');
  });
  mask.addEventListener('click', e => { if (e.target === mask) close(); });
  document.addEventListener('keydown', onKey);
  renderFields();
}
$('#nBtnAdd').addEventListener('click', () => channelEditor(null));
$('#nBtnNone').addEventListener('click', async () => {
  if (!confirm('把所有事件的通知关掉？渠道配置会保留。')) return;
  const map = {};
  (S.notify.events || []).forEach(e => { map[e.code] = false; });
  const r = await api('/api/notify/policy', { events: map }).catch(() => null);
  if (!r || !r.ok) return errToast(r);
  S.notify = r; renderNotify();
  toast('已全部关闭', '需要哪条再单独打开', 'bell');
});
$('#nBtnRec').addEventListener('click', async () => {
  const map = {};
  (S.notify.events || []).forEach(e => { map[e.code] = !!e.default; });
  const r = await api('/api/notify/policy', { events: map }).catch(() => null);
  if (!r || !r.ok) return errToast(r);
  S.notify = r; renderNotify();
  toast('已恢复推荐订阅', '', 'check');
});
$('#nBtnClear').addEventListener('click', async () => {
  if (!confirm('清空推送历史？')) return;
  const r = await api('/api/notify/history/clear', {}).catch(() => null);
  if (!r || !r.ok) return errToast(r);
  toast('推送历史已清空', '', 'trash');
  loadHistory();
});
$('#polEnabled').addEventListener('click', async e => {
  const want = e.currentTarget.dataset.on !== 'true';
  const r = await api('/api/notify/policy', { enabled: want }).catch(() => null);
  if (!r || !r.ok) return errToast(r);
  S.notify = r; renderNotify();
  toast(want ? '通知已启用' : '通知已关闭', want ? '' : '不再发送任何消息', want ? 'check' : 'clock');
});
$('#polQuietSw').addEventListener('click', async e => {
  const want = e.currentTarget.dataset.on !== 'true';
  const from = $('#polQuietFrom').value || '23:00';
  const to = $('#polQuietTo').value || '07:00';
  const r = await api('/api/notify/policy', { quiet: want ? (from + '-' + to) : '' }).catch(() => null);
  if (!r || !r.ok) return errToast(r);
  S.notify = r; renderNotify();
  toast(want ? '静默时段已开启' : '静默时段已关闭', want ? from + ' – ' + to + '（紧急事件照发）' : '', 'clock');
});
['#polQuietFrom', '#polQuietTo'].forEach(sel => {
  $(sel).addEventListener('change', async () => {
    if ($('#polQuietSw').dataset.on !== 'true') return;
    const r = await api('/api/notify/policy', {
      quiet: ($('#polQuietFrom').value || '23:00') + '-' + ($('#polQuietTo').value || '07:00')
    }).catch(() => null);
    if (!r || !r.ok) return errToast(r);
    S.notify = r; renderNotify();
    toast('静默时段已更新', '', 'check');
  });
});
$('#polDedupe').addEventListener('change', async e => {
  const r = await api('/api/notify/policy', { dedupe: Number(e.target.value) * 60 }).catch(() => null);
  if (!r || !r.ok) return errToast(r);
  S.notify = r;
  toast('去重窗口已更新', e.target.value + ' 分钟内同一事件只发一次', 'check');
});
$('#polHist').addEventListener('change', async e => {
  const r = await api('/api/notify/policy', { history_max: Number(e.target.value) }).catch(() => null);
  if (!r || !r.ok) return errToast(r);
  S.notify = r;
  toast('推送历史保留已更新', e.target.value + ' 条', 'history');
  if (S.nTab === 'history') loadHistory();
});
$$('#nSeg button').forEach(b => b.addEventListener('click', () => {
  $$('#nSeg button').forEach(x => x.removeAttribute('data-on'));
  b.setAttribute('data-on', 'true');
  const t = b.dataset.t;
  S.nTab = t;
  for (const k of ['channels', 'events', 'history']) {
    const box = document.getElementById('n-tab-' + k);
    box.style.display = (k === t) ? (k === 'channels' || k === 'events' ? 'flex' : 'block') : 'none';
  }
  $('#nBtnAdd').classList.toggle('hide', t !== 'channels');
  $('#nBtnNone').classList.toggle('hide', t !== 'events');
  $('#nBtnRec').classList.toggle('hide', t !== 'events');
  $('#nBtnClear').classList.toggle('hide', t !== 'history');
  if (t === 'history') loadHistory();
}));

/* ==========================================================================
   路由器设置（字段全部来自 /api/state 的 settings，前端不写死）
   ========================================================================== */
async function loadSettings() {
  const st = await api('/api/state').catch(() => null);
  if (st) { S.state = st; }
  renderSettings();
}
function renderSettings() {
  const st = S.state;
  if (!st) return;
  const ov = st.overview || {};
  $('#routerSub').textContent = [ov.router_host, ov.router_user].filter(Boolean).join(' · ');
  const groups = st.settings || [];
  const host = (S.info && S.info.info) || {};
  $('#routerFields').innerHTML = '';
  $('#behaviorFields').innerHTML = '';
  groups.forEach(g => {
    const holder = g.group === '路由器连接' ? $('#routerFields')
      : g.group === '运行行为' ? $('#behaviorFields') : null;
    if (!holder) return;
    (g.fields || []).forEach(f => holder.appendChild(fieldRow(f)));
  });
  const ready = ov.password_set;
  const badge = $('#connBadge');
  const okConn = !!(S.info && S.info.ok);
  badge.className = 'badge ' + (okConn ? 'badge-run' : 'badge-plain');
  badge.innerHTML = '<span class="dot"></span>' + (okConn ? '连接正常' : (ready ? '未连接' : '未配置密码'));
}
function fieldRow(f) {
  const row = el('div', 'fieldrow');
  const t = el('div', 't', '<b>' + escHtml(f.label) + '</b>'
    + (f.help ? '<span>' + escHtml(f.help) + '</span>' : ''));
  const ctl = el('div', 'ctl');
  ctl.style.width = f.kind === 'bool' ? 'auto' : '260px';
  const id = 'set-' + f.key;
  if (f.kind === 'bool') {
    const b = el('button', 'sw');
    b.dataset.on = f.value ? 'true' : 'false';
    b.dataset.key = f.key;
    b.dataset.kind = 'bool';
    b.addEventListener('click', () => { b.dataset.on = b.dataset.on === 'true' ? 'false' : 'true'; });
    ctl.appendChild(b);
  } else if (f.kind === 'select') {
    const s = el('select', 'sel');
    s.id = id; s.dataset.key = f.key; s.dataset.kind = 'select';
    s.innerHTML = (f.choices || []).map(c => '<option value="' + escAttr(c) + '"'
      + (String(c) === String(f.value) ? ' selected' : '') + '>' + escHtml(c) + '</option>').join('');
    ctl.appendChild(s);
  } else if (f.secret) {
    const i = el('input', 'inp');
    i.type = 'password'; i.id = id; i.dataset.key = f.key; i.dataset.kind = 'secret';
    i.placeholder = f.is_set ? '已设置，留空表示不修改' : (f.placeholder || '');
    ctl.appendChild(i);
  } else {
    const i = el('input', 'inp');
    i.type = (f.kind === 'int' || f.kind === 'float') ? 'number' : 'text';
    i.id = id; i.dataset.key = f.key; i.dataset.kind = f.kind;
    i.value = f.value == null ? '' : f.value;
    if (f.placeholder) i.placeholder = f.placeholder;
    ctl.appendChild(i);
  }
  row.appendChild(t);
  row.appendChild(ctl);
  return row;
}
$('#btnSaveSettings').addEventListener('click', async () => {
  const patch = {};
  $$('#p-router [data-key]').forEach(n => {
    const k = n.dataset.key, kind = n.dataset.kind;
    if (kind === 'bool') patch[k] = n.dataset.on === 'true';
    else if (kind === 'secret') { if (n.value) patch[k] = n.value; }
    else if (n.value !== '') patch[k] = n.value;
  });
  const r = await api('/api/settings', patch).catch(() => null);
  if (!r || !r.ok) return errToast(r);
  S.state = Object.assign(S.state || {}, { overview: r.overview, settings: r.settings });
  renderSettings();
  toast('设置已保存', (r.notes || []).join('；') || '立即生效', 'check');
  refreshState();
});
$('#btnTest').addEventListener('click', async () => {
  const btn = $('#btnTest');
  btn.disabled = true;
  const r = await api('/api/router/test', {}).catch(() => null);
  btn.disabled = false;
  if (r && r.ok) {
    const d = r.device || {};
    toast('连上了路由器', [d.product, d.model].filter(Boolean).join(' · ') || '', 'check');
  } else errToast(r);
  loadInfo();
});

/* ==========================================================================
   关于 / 诊断信息
   ========================================================================== */
function renderAbout() {
  const st = S.state || {};
  const q = { running: !!S.authed };
  delete q.running;
  const o = st.overview || {};
  const s = st.status || {};
  const diag = {
    version: S.version || '',
    router: o.router_host || '',
    rules: (o.rules || []).length,
    poll_interval: null,
    last_tick: s.last_tick_at || null,
    last_success: s.last_success_at || null,
    ok: s.ok,
    failures: s.consecutive_failures || 0,
    writes_total: s.total_writes || 0,
    firewall_on: s.firewall_ipv6_enabled,
    dry_run: !!s.dry_run,
    logged_in: !!s.logged_in,
    channels: (S.notify && (S.notify.channels || []).length) || 0,
    tasks: (S.tasks && (S.tasks.tasks || []).length) || 0,
  };
  const setv = (S.state && S.state.settings || []).flatMap(g => g.fields || [])
    .find(f => f.key === 'POLL_INTERVAL');
  if (setv) diag.poll_interval = Number(setv.value) || null;
  $('#diagPre').textContent = JSON.stringify(diag, null, 2);
  $('#countersTxt').textContent = '当前累计写入 ' + (s.total_writes || 0) + ' 次';
}
$('#btnCopyDiag').addEventListener('click', () => {
  const t = $('#diagPre').textContent;
  if (copyText(t)) toast('诊断信息已复制', '粘到 Issue 里就行', 'check');
  else toast('复制失败', '手动选中复制', 'alert');
});
$('#btnCopyImage').addEventListener('click', () => {
  const img = 'aaron2024s/ipv6sync:latest';
  if (copyText(img)) toast('镜像名已复制', 'docker pull ' + img, 'check');
  else toast('复制失败', '手动选中复制', 'alert');
});
$('#btnResetCounters').addEventListener('click', async () => {
  const btn = $('#btnResetCounters');
  btn.disabled = true;
  try {
    const j = await api('/api/counters/reset', {});
    if (j && j.ok === false) throw new Error(j.error || '失败');
    toast('累计写入已清零', '只影响统计数字，白名单不受影响', 'check');
    const st = await api('/api/state').catch(() => null);
    if (st) S.state = st;
    renderAbout();
  } catch (e) {
    toast('重置失败', '请稍后再试', 'alert');
  } finally { btn.disabled = false; }
});

/* ==========================================================================
   导航 / 主题 / 刷新
   ========================================================================== */
const CTX_TEXT = {
  devices: '设备', firewall: 'IPv6 防火墙', tasks: '计划任务',
  notify: '系统 · 通知', router: '系统 · 路由器设置', about: '系统 · 关于',
};
const PAGE_LOAD = {
  devices: async () => { await loadInfo(); await loadHosts(); },
  firewall: loadFirewall,
  tasks: loadTasks,
  notify: loadNotify,
  router: async () => { await loadInfo(); await loadSettings(); },
  about: async () => { renderAbout(); },
};
$$('.ni[data-page]').forEach(b => b.addEventListener('click', () => {
  $$('.ni[data-page]').forEach(x => x.removeAttribute('aria-current'));
  b.setAttribute('aria-current', 'true');
  const p = b.dataset.page;
  S.page = p;
  $$('.page').forEach(x => x.classList.add('hide'));
  document.getElementById('p-' + p).classList.remove('hide');
  document.getElementById('ctx').textContent = CTX_TEXT[p] || '';
  document.querySelector('.main').scrollTop = 0;
  if (window.closeNav) window.closeNav();
  const fn = PAGE_LOAD[p];
  if (fn) Promise.resolve(fn()).catch(() => {});
}));
/* 主题三态：跟随系统 → 深色 → 浅色 → 跟随系统，选择记忆在浏览器本地。
   「跟随系统」时按 prefers-color-scheme 落到具体的深色/浅色，
   并且系统自己改了深浅也会跟着变（不用刷新）。 */
const THEME_KEY = 'hrc-theme';
const THEMES = [['auto', 'auto', '跟随系统'], ['dark', 'moon', '深色'], ['light', 'sun', '浅色']];
const THEME_NEXT = { auto: 'dark', dark: 'light', light: 'auto' };
const mqDark = window.matchMedia('(prefers-color-scheme: dark)');
function themeChoice() {
  try { return localStorage.getItem(THEME_KEY) || 'auto'; } catch (e) { return 'auto'; }
}
function applyTheme(choice) {
  const t = THEMES.find(x => x[0] === choice) ? choice : 'auto';
  const real = t === 'auto' ? (mqDark.matches ? 'dark' : 'light') : t;
  document.documentElement.dataset.theme = real;
  const [, icon, label] = THEMES.find(x => x[0] === t);
  const btn = $('#themeBtn');
  btn.innerHTML = '<svg class="i"><use href="#i-' + icon + '"/></svg>'
    + '<span class="tlabel">' + label + '</span>';
  btn.title = '切换界面主题：跟随系统 → 深色 → 浅色（当前 ' + label + '）';
}
$('#themeBtn').addEventListener('click', () => {
  const next = THEME_NEXT[themeChoice()] || 'auto';
  try { localStorage.setItem(THEME_KEY, next); } catch (e) { }
  applyTheme(next);
});
const onSysTheme = () => { if (themeChoice() === 'auto') applyTheme('auto'); };
if (mqDark.addEventListener) mqDark.addEventListener('change', onSysTheme);
else if (mqDark.addListener) mqDark.addListener(onSysTheme);
applyTheme(themeChoice());
/* 移动端侧栏抽屉 */
let scrim = null;
const shell = document.querySelector('.shell');
$('#menuBtn').addEventListener('click', () => {
  shell.classList.add('navopen');
  if (!scrim) {
    scrim = document.createElement('div');
    scrim.className = 'scrim';
    scrim.addEventListener('click', () => closeNav());
    document.body.appendChild(scrim);
  }
});
function closeNav() {
  shell.classList.remove('navopen');
  if (scrim) { scrim.remove(); scrim = null; }
}
window.closeNav = closeNav;
/* 桌面端收起侧栏 */
$('#btnCollapse').addEventListener('click', () => {
  shell.classList.toggle('collapsed');
  try { localStorage.setItem('hrc-collapsed', shell.classList.contains('collapsed') ? '1' : '0'); }
  catch (e) { }
});
try {
  if (localStorage.getItem('hrc-collapsed') === '1') shell.classList.add('collapsed');
} catch (e) { }

$$('.rc-acts [data-op]').forEach(b => b.addEventListener('click', () => quickOp(b.dataset.op)));
$('#devQ').addEventListener('input', e => { S.devQuery = e.target.value; renderDevices(); });
$('#devType').addEventListener('change', e => { S.devType = e.target.value; renderDevices(); });

/* 轻量轮询：只拉内存里的状态（不打路由器） */
async function refreshState() {
  const st = await api('/api/state').catch(() => null);
  if (!st) return;
  S.state = st;
  renderCounts();
  if (S.page === 'devices') renderInfo();
  if (S.page === 'router') renderSettings();
  if (S.page === 'about') renderAbout();
}

/* 启动 */
async function boot() {
  const v = await api('/api/version').catch(() => null);
  if (v) S.version = v.version || '';
  await refreshState();
  await Promise.all([
    loadTasks(),
    loadNotify(),
    loadInfo(),
    loadHosts(),
  ]);
  renderSettings();
  renderAbout();
}
(async function start() {
  try {
    const s = await (await fetch('/api/session')).json();
    if (s && s.authed) {
      S.authed = true;
      hideGate();
      await boot();
      setInterval(refreshState, 5000);
    } else showGate();
  } catch (e) { showGate(); }
})();
</script>
</body>
</html>
'''
