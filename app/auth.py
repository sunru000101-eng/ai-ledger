"""账号体系：邀请码注册 + 用户名密码登录 + 会话token。
全部用 Python 标准库（scrypt 哈希 + secrets token），不引入新依赖。"""
import datetime
import hashlib
import re
import secrets

from . import config, db

_USERNAME_RE = re.compile(r"^[\w一-龥]{2,20}$")


def _hash_pw(password: str, salt: str = "") -> str:
    salt = salt or secrets.token_hex(16)
    h = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1)
    return f"{salt}${h.hex()}"


def _verify_pw(password: str, stored: str) -> bool:
    try:
        salt = stored.split("$", 1)[0]
        return secrets.compare_digest(_hash_pw(password, salt), stored)
    except (ValueError, IndexError):
        return False


def _new_session(user_id: int) -> str:
    token = secrets.token_hex(32)
    expires = (datetime.datetime.now() + datetime.timedelta(days=config.SESSION_DAYS)
               ).strftime("%Y-%m-%d %H:%M:%S")
    db.execute("INSERT INTO sessions(token, user_id, expires_at) VALUES (?,?,?)",
               (token, user_id, expires))
    return token


def register(username: str, password: str, invite_code: str):
    """返回 (token, error)。error 为 None 表示成功"""
    if not config.INVITE_CODE:
        return None, "注册暂未开放"
    if invite_code.strip() != config.INVITE_CODE:
        return None, "邀请码不对，找站长要一个～"
    username = username.strip()
    if not _USERNAME_RE.fullmatch(username):
        return None, "用户名需2-20位（中文/字母/数字/下划线）"
    if len(password) < 6:
        return None, "密码至少6位"
    if db.query_one("SELECT id FROM users WHERE username = ?", (username,)):
        return None, "这个用户名被抢先了，换一个吧"
    row = db.execute(
        "INSERT INTO users(username, pw_hash, created_at) VALUES (?,?,?) RETURNING id",
        (username, _hash_pw(password), db.now_str()))
    return _new_session(row["id"]), None


def login(username: str, password: str):
    """返回 (token, error)"""
    row = db.query_one("SELECT id, pw_hash FROM users WHERE username = ?",
                       (username.strip(),))
    if not row or not _verify_pw(password, row["pw_hash"]):
        return None, "用户名或密码不对"
    return _new_session(row["id"]), None


def logout(token: str):
    if token:
        db.execute("DELETE FROM sessions WHERE token = ?", (token,))


def user_from_token(token: str):
    """token有效则返回 {id, username}，否则 None"""
    if not token or len(token) != 64:
        return None
    row = db.query_one(
        "SELECT u.id AS id, u.username AS username, s.expires_at AS expires_at "
        "FROM sessions s JOIN users u ON u.id = s.user_id WHERE s.token = ?", (token,))
    if not row:
        return None
    if row["expires_at"] < db.now_str():
        db.execute("DELETE FROM sessions WHERE token = ?", (token,))
        return None
    return {"id": row["id"], "username": row["username"]}
