# -*- coding: utf-8 -*-
"""首次初始化（网页设置访问密码）与凭据存储。

单密码模式（参考 dockhelm）：没有用户名，只问密码。重点不是字段好不好看，
而是这几条安全性质：
  · setup 只允许成功一次 —— 第二次必须 403，谁晚到谁吃亏都不能重来；
  · auth.json 里绝不能出现明文密码；
  · 弱密码在服务端被拒（前端提示只是体验，不是防线）；
  · 改密码要旧密码，改完其他会话作废。
"""
import json
import os
import socket
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.auth import AuthError, AuthStore     # noqa: E402
from app.webui import WebUI                   # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_webui import FakeNode, call, free_port   # noqa: E402


def tmpfile(name: str) -> str:
    return os.path.join(tempfile.mkdtemp(), name)


class AuthStoreTest(unittest.TestCase):
    def setUp(self):
        self.store = AuthStore(tmpfile("auth.json"))

    def test_create_then_verify(self):
        self.assertFalse(self.store.exists())
        self.store.create("Corr3ct-Horse!")
        self.assertTrue(self.store.exists())
        # 新文件不再写 username；username() 是兼容旧文件的显示用回退
        self.assertEqual(self.store.username(), "admin")
        self.assertTrue(self.store.verify("Corr3ct-Horse!"))
        self.assertFalse(self.store.verify("wrong"))

    def test_create_only_once(self):
        self.store.create("Corr3ct-Horse!")
        with self.assertRaises(AuthError):
            self.store.create("another-Pass1!")
        self.assertEqual(self.store.username(), "admin")

    def test_weak_password_rejected(self):
        # 长度不够：至少 8 位
        for pw in ("", "short", "aB1!", "a" * 7):
            with self.assertRaises(AuthError):
                self.store.create(pw)
        # 长度够但种类不全：必须字母、数字、特殊字符三类齐全
        for pw in ("abcdefgh",        # 只有字母
                   "12345678",        # 只有数字
                   "!@#$%^&*",        # 只有特殊字符
                   "abcd1234",        # 缺特殊字符
                   "abcd!@#$",        # 缺数字
                   "1234!@#$"):       # 缺字母
            with self.assertRaises(AuthError):
                self.store.create(pw)
        self.assertFalse(self.store.exists(), "失败创建不能留下半截文件")

    def test_password_kinds_boundary_ok(self):
        # 恰好 8 位且三类齐全 = 合法
        self.store.create("Ab1!Ab1!")
        self.assertTrue(self.store.verify("Ab1!Ab1!"))

    def test_no_plaintext_on_disk(self):
        self.store.create("Corr3ct-Horse!")
        with open(self.store.path, encoding="utf-8") as f:
            blob = f.read()
        self.assertNotIn("Corr3ct-Horse!", blob)
        rec = json.loads(blob)
        self.assertEqual(rec["password"]["algo"], "scrypt")
        self.assertNotEqual(rec["password"]["hash"],
                            "Corr3ct-Horse!")

    def test_set_password_overwrites_without_old(self):
        """环境变量重置的入口：无条件覆盖，不问旧密码。"""
        self.store.create("Corr3ct-Horse!")
        self.store.set_password("another-Pass1!")
        self.assertTrue(self.store.verify("another-Pass1!"))
        self.assertFalse(self.store.verify("Corr3ct-Horse!"))
        with self.assertRaises(AuthError):
            self.store.set_password("short")

    def test_lock_policy_defaults_and_clamp(self):
        """登录保护策略：默认 5 次/5 分钟；越界值夹回区间而不是拒绝。"""
        self.store.create("Corr3ct-Horse!")
        self.assertEqual(self.store.policy(),
                         {"max_failures": 5, "minutes": 5})
        pol = self.store.set_policy(999, 0)
        self.assertEqual(pol, {"max_failures": 20, "minutes": 1})
        pol = self.store.set_policy("x", None)      # 坏值回默认
        self.assertEqual(pol, {"max_failures": 5, "minutes": 5})
        # 持久化：换个实例读出来还是保存的值
        self.store.set_policy(7, 12)
        again = AuthStore(self.store.path)
        self.assertEqual(again.policy(), {"max_failures": 7, "minutes": 12})

    def test_legacy_username_file_still_verifies(self):
        """旧版本 auth.json（username + password）升级后必须还能登录。"""
        from app.auth import _hash
        rec = {"username": "boss", "password": _hash("Corr3ct-Horse!"),
               "created_at": 0, "updated_at": 0}
        with open(self.store.path, "w", encoding="utf-8") as f:
            json.dump(rec, f)
        self.assertEqual(self.store.username(), "boss")
        self.assertTrue(self.store.verify("Corr3ct-Horse!"))
        self.assertFalse(self.store.verify("wrong"))

    def test_update_password_requires_old(self):
        self.store.create("Corr3ct-Horse!")
        with self.assertRaises(AuthError):
            self.store.update_password("wrong-old", "another-Pass1!")
        self.store.update_password("Corr3ct-Horse!", "another-Pass1!")
        self.assertTrue(self.store.verify("another-Pass1!"))
        self.assertFalse(self.store.verify("Corr3ct-Horse!"))

    def test_corrupt_file_fails_closed(self):
        self.store.create("Corr3ct-Horse!")
        with open(self.store.path, "w", encoding="utf-8") as f:
            f.write("{not json")
        self.assertIsNone(self.store.load())
        self.assertFalse(self.store.verify("Corr3ct-Horse!"),
                         "文件坏了必须拒登，绝不能放行")


class SetupHttpTest(unittest.TestCase):
    """真起 HTTP 服务，把「打开网页创建管理员」完整走一遍。"""

    def setUp(self):
        self.port = free_port()
        self.ui = WebUI(FakeNode(), "127.0.0.1", self.port, tmpfile("auth.json"))
        self.srv = self.ui.start()
        self.base = f"http://127.0.0.1:{self.port}"

    def tearDown(self):
        self.ui.stop()

    def test_setup_flow_then_locked_forever(self):
        # 未初始化：session 标明 setupDone=false
        code, j, _ = call(self.base, "/api/session")
        self.assertFalse(j["authed"])
        self.assertFalse(j["setupDone"])

        # 弱密码被拒
        code, j, _ = call(self.base, "/api/setup", "POST",
                          {"password": "short",
                           "password2": "short"})
        self.assertEqual(code, 400)
        self.assertFalse(j["ok"])

        # 两次不一致被拒
        code, j, _ = call(self.base, "/api/setup", "POST",
                          {"password": "Corr3ct-Horse!",
                           "password2": "different-Pass1!"})
        self.assertEqual(code, 400)

        # 正常创建：签发会话
        code, j, hdr = call(self.base, "/api/setup", "POST",
                            {"password": "Corr3ct-Horse!",
                             "password2": "Corr3ct-Horse!"})
        self.assertEqual(code, 200, j)
        self.assertEqual(j["user"], "admin")
        cookie = hdr.get("Set-Cookie", "").split(";")[0]
        self.assertTrue(cookie)

        # 创建成功后：入口永久关闭
        code, j, _ = call(self.base, "/api/setup", "POST",
                          {"password": "attacker-Pass1!",
                           "password2": "attacker-Pass1!"})
        self.assertEqual(code, 403, "第二次创建必须被拒，不能覆盖")
        code, j, _ = call(self.base, "/api/session")
        self.assertTrue(j["setupDone"])

        # 旧口令失效、新口令可登录
        code, _, _ = call(self.base, "/api/login", "POST",
                          {"password": "attacker-Pass1!"})
        self.assertEqual(code, 401)
        code, j, _ = call(self.base, "/api/login", "POST",
                          {"password": "Corr3ct-Horse!"})
        self.assertEqual(code, 200)

    def test_change_password_invalidates_other_sessions(self):
        self.ui.auth.create("Corr3ct-Horse!")

        # 两个独立会话
        _, _, h1 = call(self.base, "/api/login", "POST",
                        {"password": "Corr3ct-Horse!"})
        _, _, h2 = call(self.base, "/api/login", "POST",
                        {"password": "Corr3ct-Horse!"})
        c1 = h1.get("Set-Cookie", "").split(";")[0]
        c2 = h2.get("Set-Cookie", "").split(";")[0]

        # 改密码：旧密码错 → 400
        code, j, _ = call(self.base, "/api/password", "POST",
                          {"old": "wrong", "new": "another-Pass1!"},
                          cookie=c1)
        self.assertEqual(code, 400)

        # 改密码成功；当前会话存活，其他会话作废
        code, j, _ = call(self.base, "/api/password", "POST",
                          {"old": "Corr3ct-Horse!",
                           "new": "another-Pass1!"},
                          cookie=c1)
        self.assertEqual((code, j["ok"]), (200, True))
        code, j, _ = call(self.base, "/api/state", cookie=c1)
        self.assertEqual((code, j["authed"]), (200, True), "当前会话不能被自己改密码踢掉")
        code, j, _ = call(self.base, "/api/state", cookie=c2)
        # /api/state 对未登录温和降级（200 + authed:false），作废体现在这里
        self.assertEqual((code, j["authed"]), (200, False), "其他会话必须作废")

        # 新密码登录、旧密码失效
        code, _, _ = call(self.base, "/api/login", "POST",
                          {"password": "Corr3ct-Horse!"})
        self.assertEqual(code, 401)
        code, _, _ = call(self.base, "/api/login", "POST",
                          {"password": "another-Pass1!"})
        self.assertEqual(code, 200)

    def test_setup_and_login_also_require_same_origin(self):
        """创建/登录虽然还没有会话，也必须过同源校验（审查 H-1 / H-2）。

        没会话不等于可以放行来源：否则任意网页都能跨站抢注管理员
        （初始化窗口内），或拿着登录接口当无来源限制的口令探测口。
        """
        self.ui.auth.create("Corr3ct-Horse!")
        code, _, _ = call(self.base, "/api/login", "POST",
                          {"password": "Corr3ct-Horse!"},
                          origin="http://evil.example")
        self.assertEqual(code, 403, "跨站登录必须拒绝")
        code, _, _ = call(self.base, "/api/login", "POST",
                          {"password": "Corr3ct-Horse!"})
        self.assertEqual(code, 200, "同源/无 Origin 的登录照常")
        cookie = "ipv6sync_web=" + next(iter(self.ui._tokens))
        code, _, _ = call(self.base, "/api/sync", "POST", {},
                          cookie=cookie, origin="http://evil.example")
        self.assertEqual(code, 403, "动作接口的 CSRF 防线必须还在")


if __name__ == "__main__":
    unittest.main()
