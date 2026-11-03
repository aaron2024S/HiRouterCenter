# -*- coding: utf-8 -*-
"""安全回归：端点 × 身份 × 来源 的权限矩阵 + 版本一致性 + 健壮性。

这组用例的由来：2026-11-03 的安全审查里，442 条用例全绿，却漏掉了
「未登录能爆破改密」「跨站能抢注管理员」这两个高危。根因不是测得少，
而是**没人问"不该能调的能不能调"**。所以这里补的是那张表，而不是再写
一堆"以正确身份调正确接口"的用例。

    python -m unittest tests.test_security_matrix -v
"""
import json
import os
import re
import socket
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import __version__                     # noqa: E402
from app.auth import AuthStore                  # noqa: E402
from app.webui import WebUI                     # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NO_PROXY = urllib.request.build_opener(urllib.request.ProxyHandler({}))

PASSWORD = "Corr3ct-Horse!"


class StubNode:
    """权限矩阵只关心"有没有走到处理逻辑"，不关心业务返回值。"""

    def __getattr__(self, name):
        def _any(*a, **kw):
            return {"ok": True, "called": name}
        return _any


def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def call(base, path, method="GET", body=None, headers=None):
    data = json.dumps(body).encode() if body is not None else None
    h = {"Content-Type": "application/json"} if data is not None else {}
    h.update(headers or {})
    req = urllib.request.Request(base + path, data=data, headers=h, method=method)
    try:
        with NO_PROXY.open(req, timeout=15) as r:
            return r.status, r.read().decode("utf-8", "replace"), dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace"), dict(e.headers)


class AuthMatrixTest(unittest.TestCase):
    """每个改状态的 POST：未登录必须 401、跨站必须 403、错类型必须 415。"""

    # 除 setup/login/logout（本来就不需要会话）之外的全部动作路由
    ROUTES = [
        "/api/settings", "/api/sync", "/api/router/test", "/api/wol",
        "/api/router/firewall", "/api/counters/reset", "/api/events/clear",
        "/api/events/max", "/api/rules", "/api/router/whitelist/delete",
        "/api/router/whitelist/update", "/api/notify/test",
        "/api/notify/channels", "/api/notify/channel/test", "/api/notify/policy",
        "/api/notify/history/clear", "/api/notify/dedupe/reset",
        "/api/router/action", "/api/host/type", "/api/host/rename",
        "/api/host/limit", "/api/host/blacklist", "/api/tasks/save",
        "/api/tasks/delete", "/api/tasks/toggle", "/api/tasks/run",
        "/api/tasks/cron_check", "/api/password",
    ]

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.port = free_port()
        cls.ui = WebUI(StubNode(), "127.0.0.1", cls.port,
                       os.path.join(cls.tmp, "auth.json"))
        cls.ui.auth.create("admin", PASSWORD)
        cls.ui.start()
        cls.base = f"http://127.0.0.1:{cls.port}"
        time.sleep(0.3)
        code, _, hdrs = call(cls.base, "/api/login", "POST",
                             {"user": "admin", "password": PASSWORD})
        assert code == 200, f"测试自身登录失败：{code}"
        cls.cookie = "ipv6sync_web=" + cls.ui._new_token("admin")

    @classmethod
    def tearDownClass(cls):
        cls.ui.stop()

    def test_unauthenticated_post_is_rejected(self):
        """未登录不能调任何动作接口 —— 尤其 /api/password（审查 H-1）。"""
        bad = []
        for route in self.ROUTES:
            code, _, _ = call(self.base, route, "POST", {})
            if code != 401:
                bad.append(f"{route} -> {code}")
        self.assertEqual(bad, [], "未登录却放行的接口：" + "，".join(bad))

    def test_cross_site_post_is_rejected(self):
        """带合法会话也不行：跨站来源一律 403（含 setup/login/logout）。"""
        bad = []
        for route in self.ROUTES + ["/api/setup", "/api/login", "/api/logout"]:
            code, _, _ = call(self.base, route, "POST", {},
                              {"Origin": "http://evil.example",
                               "Cookie": self.cookie})
            if code != 403:
                bad.append(f"{route} -> {code}")
        self.assertEqual(bad, [], "跨站却放行的接口：" + "，".join(bad))

    def test_non_json_post_is_rejected(self):
        """只收 application/json：跨站 form / text-plain 简单请求发不出来。"""
        bad = []
        for route in self.ROUTES + ["/api/setup", "/api/login"]:
            code, _, _ = call(self.base, route, "POST", None,
                              {"Content-Type": "text/plain", "Cookie": self.cookie})
            if code != 415:
                bad.append(f"{route} -> {code}")
        self.assertEqual(bad, [], "错类型却放行的接口：" + "，".join(bad))

    def test_cross_site_get_does_not_leak_state(self):
        """/api/state 未登录只回 authed=false，不带任何配置。"""
        code, txt, _ = call(self.base, "/api/state")
        j = json.loads(txt)
        self.assertEqual((code, j.get("authed")), (200, False))
        self.assertNotIn("settings", j)


class SetupAndPasswordTest(unittest.TestCase):
    """首次初始化与改密的边界（审查 H-1 / H-2）。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.port = free_port()
        self.auth_file = os.path.join(self.tmp, "auth.json")
        self.ui = WebUI(StubNode(), "127.0.0.1", self.port, self.auth_file)
        self.ui.start()
        self.base = f"http://127.0.0.1:{self.port}"
        time.sleep(0.2)

    def tearDown(self):
        self.ui.stop()

    def test_cross_site_setup_cannot_grab_admin(self):
        """首次初始化的窗口期不能被任意网页抢注（审查 H-2）。"""
        for ctype in ("text/plain", "application/json"):
            code, _, _ = call(self.base, "/api/setup", "POST",
                              {"user": "pwned", "password": "Pwn3d-Pass!",
                               "password2": "Pwn3d-Pass!"},
                              {"Origin": "http://evil.example",
                               "Content-Type": ctype})
            self.assertIn(code, (403, 415))
        code, txt, _ = call(self.base, "/api/setup-status")
        self.assertFalse(json.loads(txt)["setupDone"], "管理员绝不能被跨站创建")

    def test_setup_status_does_not_leak_username(self):
        """未认证接口不回显管理员名（审查 M-2）。"""
        self.ui.auth.create("admin", PASSWORD)
        code, txt, _ = call(self.base, "/api/setup-status")
        j = json.loads(txt)
        self.assertTrue(j["setupDone"])
        self.assertNotIn("username", j, "用户名不该白送")

    def test_password_change_requires_session(self):
        """未登录改密必须 401，且原密码不受影响（审查 H-1）。"""
        self.ui.auth.create("admin", PASSWORD)
        for i in range(5):
            code, _, _ = call(self.base, "/api/password", "POST",
                              {"old": f"guess{i}", "new": "Attacker-Pass1!"})
            self.assertEqual(code, 401)
        code, _, _ = call(self.base, "/api/password", "POST",
                          {"old": PASSWORD, "new": "Attacker-Pass1!"})
        self.assertEqual(code, 401, "知道旧密码也必须先登录")
        self.assertTrue(self.ui.auth.verify("admin", PASSWORD), "密码不该被改掉")

    def test_broken_auth_file_allows_recovery(self):
        """auth.json 半截损坏 → 允许重建，并把坏文件留证（审查 M-3）。"""
        with open(self.auth_file, "w", encoding="utf-8") as f:
            f.write('{"username": "admin", "password": {"algo"')
        code, txt, _ = call(self.base, "/api/setup-status")
        j = json.loads(txt)
        self.assertFalse(j["setupDone"], "损坏时入口必须重新打开")
        self.assertTrue(j["broken"], "要能告诉用户是文件坏了")
        code, _, _ = call(self.base, "/api/setup", "POST",
                          {"user": "admin", "password": PASSWORD,
                           "password2": PASSWORD})
        self.assertEqual(code, 200, "损坏后必须能自救")
        backups = [f for f in os.listdir(self.tmp) if "broken" in f]
        self.assertTrue(backups, "坏文件要留证，不能静默覆盖")

    def test_oversized_body_is_413_and_closes(self):
        """超大请求体回 413 + 关连接（审查 L-1：不读完会请求错位）。

        服务端回完 413 就关连接、不读这 2MB，所以客户端有时会在"还没写完"
        就撞上连接关闭 —— 这也算通过（重点是**不把残留字节留给下一个请求**，
        也不把 2MB 读进内存）。
        """
        req = urllib.request.Request(
            self.base + "/api/login",
            data=b'{"user":"a","password":"' + b"x" * (2 << 20) + b'"}',
            headers={"Content-Type": "application/json"}, method="POST")
        try:
            with NO_PROXY.open(req, timeout=15) as r:
                self.assertEqual(r.status, 413)
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 413)
        except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
            pass                       # 服务端已关连接，等价结果


class TimingSideChannelTest(unittest.TestCase):
    """用户名对不对，耗时必须同量级（审查 M-1）。"""

    def setUp(self):
        self.store = AuthStore(os.path.join(tempfile.mkdtemp(), "auth.json"))
        self.store.create("admin", PASSWORD)

    def _avg(self, user):
        ts = []
        for _ in range(3):
            t0 = time.perf_counter()
            self.store.verify(user, "definitely-wrong")
            ts.append(time.perf_counter() - t0)
        return sum(ts) / len(ts)

    def test_unknown_username_is_not_obviously_faster(self):
        known, unknown = self._avg("admin"), self._avg("nobody-here")
        ratio = max(known, unknown) / max(1e-6, min(known, unknown))
        # 短路版本这里是 400 倍以上；跑一次假 scrypt 之后应该在 1.x
        self.assertLess(ratio, 3.0, f"用户名可被时间侧信道枚举（比值 {ratio:.1f}×）")


class VersionConsistencyTest(unittest.TestCase):
    """版本号只有一个真值，其余地方不许各写一份（审查 M-7）。"""

    def _read(self, rel):
        with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
            return f.read()

    def test_all_declared_versions_match(self):
        found = {"app/__init__.py": __version__}
        m = re.search(r'fallback:\s*str\s*=\s*"([\d.]+)"',
                      self._read("offline/build_offline.py"))
        if m:
            found["offline/build_offline.py"] = m.group(1)
        m = re.search(r'^VERSION\s*=\s*"([\d.]+)"',
                      self._read("offline/pack_src.py"), re.M)
        if m:
            found["offline/pack_src.py"] = m.group(1)
        m = re.search(r'fallback:\s*str\s*=\s*"([\d.]+)"',
                      self._read("offline/validate_boot.py"))
        if m:
            found["offline/validate_boot.py"] = m.group(1)
        bad = {k: v for k, v in found.items() if v != __version__}
        self.assertEqual(bad, {}, f"版本号不一致（真值 {__version__}）")

    def test_dockerfile_has_no_hardcoded_version(self):
        """Dockerfile 不许再写死版本号 —— 它曾被漏改 3 个版本。"""
        text = self._read("Dockerfile")
        self.assertIn("ARG APP_VERSION", text)
        m = re.search(r'org\.opencontainers\.image\.version="(\d+\.\d+\.\d+)"', text)
        self.assertIsNone(m, "Dockerfile 里又写死版本号了，改成 build-arg")

    def test_readme_has_current_version_section(self):
        self.assertIn(f"### {__version__}", self._read("README.md"))


if __name__ == "__main__":
    unittest.main()
