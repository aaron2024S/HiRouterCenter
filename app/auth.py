# -*- coding: utf-8 -*-
"""控制台管理员凭据：data/auth.json 一个文件就是全部。

设计约束（与控制台定位匹配 —— 单用户、NAS 本地部署）：

* **只存哈希不存明文**。scrypt（RFC 7914）+ 独立盐，参数随文件一起落盘，
  以后调参数不影响旧文件校验。
* **单密码模式**（参考 dockhelm）：这个控制台本来就只有「管理员」一个角色，
  用户名没有存在的意义，登录/创建都只问密码。auth.json 里不再写 username；
  旧版本文件里已有的 username 照样能读出来（兼容，仅作显示用）。
* **原子写**：先写同目录临时文件再 `os.replace`，断电不会留下半截 JSON。
* **文件权限 0600**：凭据文件只留给容器主用户。Windows 上 chmod 是近似的，
  但本程序只在 Linux 容器里跑，这里是尽力而为的防御。
* **首次创建即关闭**：管理员只允许创建一次（`create` 在文件已存在时抛错），
  「重置」有两种官方途径：设环境变量 HIROUTERCENTER_PASSWORD 重启（见
  webui_from_env），或删掉 auth.json 重启 —— 等价于用磁盘权限换控制台权限。
* **登录保护策略跟着凭据文件走**（`lock` 字段）：连错几次锁、锁多久，
  设置页可调 —— 存在 auth.json 里，删文件重置后自动回到默认值。
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

# 登录保护策略的默认值与可调范围（设置页输入框与后端校验共用这一份）。
# 下限不能是 1：手滑一次就锁死自己，等于把控制台变成需要删文件的砖头；
# 上限也别放开 ——「错 200 次才锁」和没锁一样。
LOCK_DEFAULT_FAILURES = 5      # 窗口内连错 5 次
LOCK_DEFAULT_MINUTES = 5       # 锁 5 分钟
LOCK_MIN_FAILURES, LOCK_MAX_FAILURES = 2, 20
LOCK_MIN_MINUTES, LOCK_MAX_MINUTES = 1, 60
FAIL_WINDOW = 300.0            # 失败计数滑动窗口（秒），与 webui 共用

# 单密码模式下不再有「用户名错」这条路径，token 归属统一用这个占位身份
# （只进内存与日志，界面上不显示）。
CONSOLE_USER = "admin"


def _clamp(v: int, lo: int, hi: int, default: int) -> int:
    try:
        v = int(v)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, v))


def normalize_policy(failures, minutes) -> dict:
    """锁定策略的统一入口：越界值夹到合法区间而不是拒绝。

    这个数字来自界面输入，让保存因为一个数字失败没有必要；但也绝不能
    让它变成 0 或负数 —— 那等于关掉锁定或永久锁死。
    """
    return {
        "max_failures": _clamp(failures, LOCK_MIN_FAILURES, LOCK_MAX_FAILURES,
                               LOCK_DEFAULT_FAILURES),
        "minutes": _clamp(minutes, LOCK_MIN_MINUTES, LOCK_MAX_MINUTES,
                          LOCK_DEFAULT_MINUTES),
    }


DEFAULT_LOCK = normalize_policy(LOCK_DEFAULT_FAILURES, LOCK_DEFAULT_MINUTES)


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
        # 兼容两种形态：新文件只有 password；旧文件是 username + password
        if isinstance(data, dict) and isinstance(data.get("password"), dict):
            return data
        self._warn_broken("缺少 password 字段")
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
        """兼容旧文件：老 auth.json 里有 username 就用它的；新文件统一 admin。

        这个值只用于日志与会话归属，界面上不再显示、登录也不再校验。
        """
        rec = self.load()
        if rec and rec.get("username"):
            return str(rec["username"])
        return CONSOLE_USER

    # ---- 变更 ----

    def create(self, password: str) -> dict:
        """创建管理员（单密码模式，不再要用户名）。只允许成功一次 ——
        之后一切创建请求都拒绝。

        唯一的例外是**凭据文件损坏**：这时允许重建，否则控制台会锁死
        （入口关着、登录永远失败）。旧文件先改名留证，不静默覆盖。
        """
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
            rec = {"password": _hash(pw),
                   "lock": dict(DEFAULT_LOCK),
                   "created_at": int(time.time()), "updated_at": int(time.time())}
            self._write(rec)
            return rec

    def verify(self, password: str) -> bool:
        """校验密码。单密码模式只有一条路径，恒定时间问题自然消失。"""
        rec = self.load()
        if not rec:
            _verify_hash(password or "", _dummy_rec())
            return False
        return bool(_verify_hash(password or "", rec["password"]))

    def set_password(self, new: str) -> None:
        """无条件覆盖密码（忘记密码时用环境变量重置的唯一入口）。

        与 update_password 的区别：不问旧密码 —— 敢调这个的只有两种人，
        拿着 HIROUTERCENTER_PASSWORD 重启容器的宿主机主人，和测试。
        """
        pw = check_password(new)
        rec = self.load()
        with self._mu:
            if not rec:
                rec = {"lock": dict(DEFAULT_LOCK),
                       "created_at": int(time.time())}
            rec["password"] = _hash(pw)
            rec["updated_at"] = int(time.time())
            self._write(rec)

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

    # ---- 登录保护策略（存 auth.json 的 lock 字段，跟着凭据文件走） ----

    def policy(self) -> dict:
        rec = self.load()
        lock = (rec or {}).get("lock") or {}
        return normalize_policy(lock.get("max_failures"),
                                lock.get("minutes"))

    def set_policy(self, failures, minutes) -> dict:
        pol = normalize_policy(failures, minutes)
        rec = self.load()
        with self._mu:
            if not rec:
                raise AuthError("管理员尚未创建")
            rec["lock"] = pol
            rec["updated_at"] = int(time.time())
            self._write(rec)
        return pol


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
