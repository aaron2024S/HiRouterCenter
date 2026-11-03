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
import os
import re
import secrets
import tempfile
import time

ALGO = "scrypt"
N, R, P, DKLEN = 2 ** 14, 8, 1, 32          # OWASP 推荐：n=2^14, r=8, p=1
MIN_PASSWORD_LEN = 10
USERNAME_RE = re.compile(r"^[A-Za-z0-9_.\-]{2,32}$")

SCRYPT_BLOCKS = 16384                        # 仅用于文件头自检说明，不参与运算


class AuthError(ValueError):
    """凭据不合法（用户名格式 / 密码强度 / 已初始化）。"""


def check_username(name: str) -> str:
    name = (name or "").strip()
    if not USERNAME_RE.match(name):
        raise AuthError("用户名 2-32 位，只能用字母、数字、点、下划线、连字符")
    return name


def check_password(pw: str) -> str:
    if not pw or len(pw) < MIN_PASSWORD_LEN:
        raise AuthError(f"密码至少 {MIN_PASSWORD_LEN} 位")
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

    # ---- 状态 ----

    def exists(self) -> bool:
        return os.path.exists(self.path)

    def load(self) -> dict | None:
        try:
            with open(self.path, encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) and data.get("username") else None
        except (OSError, ValueError):
            return None

    def username(self) -> str:
        rec = self.load()
        return str(rec["username"]) if rec else ""

    # ---- 变更 ----

    def create(self, username: str, password: str) -> dict:
        """创建管理员。只允许成功一次 —— 之后一切创建请求都拒绝。"""
        if self.exists():
            raise AuthError("管理员已存在，请直接登录")
        name = check_username(username)
        pw = check_password(password)
        rec = {"username": name, "password": _hash(pw),
               "created_at": int(time.time()), "updated_at": int(time.time())}
        self._write(rec)
        return rec

    def verify(self, username: str, password: str) -> bool:
        rec = self.load()
        if not rec:
            return False
        ok_u = hmac.compare_digest((username or "").encode("utf-8"),
                                   str(rec["username"]).encode("utf-8"))
        return bool(ok_u and _verify_hash(password or "", rec["password"]))

    def update_password(self, old: str, new: str) -> None:
        """已登录的改密。旧密码必须对 —— 防止被劫持的会话直接换锁。"""
        rec = self.load()
        if not rec:
            raise AuthError("管理员尚未创建")
        if not _verify_hash(old or "", rec["password"]):
            raise AuthError("当前密码不正确")
        pw = check_password(new)
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
