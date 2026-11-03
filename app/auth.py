# -*- coding: utf-8 -*-
"""控制台管理员凭据：data/auth.json 一个文件就是全部。

设计约束（与控制台定位匹配 —— 单用户、NAS 本地部署）：

* **只存哈希不存明文**。scrypt（RFC 7914）+ 每账号独立盐，参数随文件一起落盘，
  以后调参数不影响旧文件校验。
* **原子写**：先写同目录临时文件再 `os.replace`，断电不会留下半截 JSON。
* **文件权限 0600**：凭据文件只留给容器主用户。Windows 上 chmod 是近似的，
  但本程序只在 Linux 容器里跑，这里是尽力而为的防御。
* **首次创建即关闭**：管理员只允许创建一次（`create` 在文件已存在时抛错），
  「重置」= 有宿主机权限的人删掉 auth.json 重启 —— 等价于用磁盘权限换控制台权限。
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import tempfile
import threading
import time

log = logging.getLogger("ipv6sync.auth")

ALGO = "scrypt"
N, R, P, DKLEN = 2 ** 14, 8, 1, 32          # OWASP 推荐：n=2^14, r=8, p=1
MIN_PASSWORD_LEN = 8
USERNAME_RE = re.compile(r"^[A-Za-z0-9_.\-]{2,32}$")


class AuthError(ValueError):
    """凭据不合法（用户名格式 / 密码强度 / 已初始化）。"""


class WrongPassword(AuthError):
    """旧密码不对 —— 调用方要把它计入登录失败账本（防爆破）。"""


# 用户名不存在时也要跑一次 scrypt，否则「用户名错」会秒回、
# 「用户名对但密码错」要 130ms+，从响应时间就能问出用户名对不对。
# 这份假记录在导入时算一次，之后每次 verify 直接复用。
_DUMMY_REC = None


def _dummy_rec() -> dict:
    global _DUMMY_REC
    if _DUMMY_REC is None:
        _DUMMY_REC = _hash("dummy-password-for-timing-only")
    return _DUMMY_REC


def check_username(name: str) -> str:
    name = (name or "").strip()
    if not USERNAME_RE.match(name):
        raise AuthError("用户名 2-32 位，只能用字母、数字、点、下划线、连字符")
    return name


def check_password(pw: str) -> str:
    """密码策略：至少 8 位，且必须同时含字母、数字、特殊字符（三类缺一不可）。

    长度放宽到 8 是因为种类要求补上了熵；特殊字符 = 非字母数字的可打印字符，
    不限定具体集合（空格也算），避免「我这个符号算不算」的困惑。
    """
    pw = pw or ""
    if len(pw) < MIN_PASSWORD_LEN:
        raise AuthError(f"密码至少 {MIN_PASSWORD_LEN} 位")
    has_letter = re.search(r"[A-Za-z]", pw)
    has_digit = re.search(r"\d", pw)
    has_special = re.search(r"[^A-Za-z0-9]", pw)
    if not (has_letter and has_digit and has_special):
        raise AuthError("密码必须同时包含字母、数字和特殊字符")
    return pw


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def _unb64(s: str) -> bytes:
    return base64.b64decode(s.encode("ascii"))


def _hash(password: str, salt: bytes | None = None) -> dict:
    salt = salt or secrets.token_bytes(16)
    dk = hashlib.scrypt(password.encode("utf-8"), salt=salt,
                        n=N, r=R, p=P, dklen=DKLEN)
    return {"algo": ALGO, "salt": _b64(salt), "n": N, "r": R, "p": P,
            "dklen": DKLEN, "hash": _b64(dk)}


def _verify_hash(password: str, rec: dict) -> bool:
    try:
        if rec.get("algo") != ALGO:
            return False                     # 未来换算法时旧文件拒登，不猜
        dk = hashlib.scrypt(password.encode("utf-8"), salt=_unb64(rec["salt"]),
                            n=int(rec.get("n", N)), r=int(rec.get("r", R)),
                            p=int(rec.get("p", P)), dklen=int(rec.get("dklen", DKLEN)))
        return hmac.compare_digest(dk, _unb64(rec["hash"]))
    except (KeyError, ValueError, TypeError):
        return False


class AuthStore:
    """auth.json 的读写与校验。线程安全靠 WebUI 侧的锁；本类只保证单文件原子。"""

    def __init__(self, path: str):
        self.path = path
        self._mu = threading.Lock()      # 并发 create / update_password 串行化
        self._last_warn = 0.0

    # ---- 状态 ----

    def exists(self) -> bool:
        return os.path.exists(self.path)

    def load(self) -> dict | None:
        try:
            with open(self.path, encoding="utf-8") as f:
                data = json.load(f)
        except FileNotFoundError:
            return None
        except (OSError, ValueError) as e:
            self._warn_broken(e)
            return None
        if isinstance(data, dict) and data.get("username"):
            return data
        self._warn_broken("缺少 username 字段")
        return None

    def _warn_broken(self, why) -> None:
        """凭据文件读不出来。这条日志是用户唯一的自救线索，别忘了打。"""
        now = time.time()
        if now - self._last_warn < 60:      # 5 秒一次的轮询别把日志刷爆
            return
        self._last_warn = now
        log.error("凭据文件无法解析（可能已损坏）：%s —— %s。"
                  "删除该文件并重启容器即可重新创建管理员。", self.path, why)

    def broken(self) -> bool:
        """文件在、但读不出可用记录 = 损坏（掉电 / 磁盘满 / 手工改坏）。"""
        return self.exists() and self.load() is None

    def username(self) -> str:
        rec = self.load()
        return str(rec["username"]) if rec else ""

    # ---- 变更 ----

    def create(self, username: str, password: str) -> dict:
        """创建管理员。只允许成功一次 —— 之后一切创建请求都拒绝。

        唯一的例外是**凭据文件损坏**：这时允许重建，否则控制台会锁死
        （入口关着、登录永远失败）。旧文件先改名留证，不静默覆盖。
        """
        name = check_username(username)
        pw = check_password(password)
        with self._mu:
            if self.exists():
                if not self.broken():
                    raise AuthError("管理员已存在，请直接登录")
                backup = f"{self.path}.broken-{int(time.time())}"
                try:
                    os.replace(self.path, backup)
                    log.error("凭据文件损坏，已备份为 %s 并重新初始化", backup)
                except OSError as e:
                    log.error("凭据文件损坏且无法备份（%s），改为直接覆盖", e)
            rec = {"username": name, "password": _hash(pw),
                   "created_at": int(time.time()), "updated_at": int(time.time())}
            self._write(rec)
            return rec

    def verify(self, username: str, password: str) -> bool:
        """校验用户名 + 密码。

        **两条路径耗时必须同量级**：用户名对不对都跑一次 scrypt。
        早期版本写成 `ok_u and _verify_hash(...)`，短路让"用户名错"只花 0.3ms，
        比"用户名对"快 400 多倍 —— 等于把用户名白送（审查报告 M-1）。
        """
        rec = self.load()
        if not rec:
            _verify_hash(password or "", _dummy_rec())
            return False
        ok_u = hmac.compare_digest((username or "").encode("utf-8"),
                                   str(rec["username"]).encode("utf-8"))
        ok_p = _verify_hash(password or "", rec["password"])
        return bool(ok_u and ok_p)

    def update_password(self, old: str, new: str) -> None:
        """已登录的改密。旧密码必须对 —— 防止被劫持的会话直接换锁。"""
        rec = self.load()
        if not rec:
            raise AuthError("管理员尚未创建")
        if not _verify_hash(old or "", rec["password"]):
            raise WrongPassword("当前密码不正确")
        pw = check_password(new)
        with self._mu:
            rec["password"] = _hash(pw)
            rec["updated_at"] = int(time.time())
            self._write(rec)


    # ---- 落盘 ----

    def _write(self, rec: dict) -> None:
        d = os.path.dirname(self.path) or "."
        os.makedirs(d, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=d, prefix=".auth-", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(rec, f, ensure_ascii=False, indent=1)
                f.write("\n")
                f.flush()
                os.fsync(f.fileno())
            os.chmod(tmp, 0o600)
            os.replace(tmp, self.path)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
