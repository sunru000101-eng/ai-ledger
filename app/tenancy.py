"""多租户与成本护栏（owner 列隔离版）。
- 游客：cookie sid → owner='g_<sid>'，首次访问自动种入演示数据，TTL 天后清理
- 注册用户：owner='u_<id>'，数据永久保存，不参与清理
- 成本护栏：游客按IP限额、注册用户按账号限额、全站总闸
"""
import datetime

from . import config, db

# 新游客的演示种子数据：(金额, 分类, 几天前, 备注)
DEMO_SEED = [
    (19, "餐饮-饮品", 0, "瑞幸咖啡"),
    (42, "餐饮-正餐", 0, "麻辣烫"),
    (28, "交通-打车", 1, "打车回家"),
    (128, "娱乐-游戏", 3, "Switch游戏"),
    (89, "日用-日用品", 5, "超市采购"),
]


def activate_guest(sid: str):
    owner = f"g_{sid}"
    db.TENANT_ID.set(owner)
    _touch(owner, "guest", seed_if_new=True)


def activate_user(user_id: int):
    owner = f"u_{user_id}"
    db.TENANT_ID.set(owner)
    _touch(owner, "user", seed_if_new=False)


def _touch(owner: str, kind: str, seed_if_new: bool):
    row = db.query_one("SELECT owner FROM tenants WHERE owner = ?", (owner,))
    if row:
        db.execute("UPDATE tenants SET last_active = ? WHERE owner = ?",
                   (db.now_str(), owner))
        return
    db.execute("INSERT INTO tenants(owner, kind, last_active) VALUES (?,?,?)",
               (owner, kind, db.now_str()))
    if seed_if_new:
        _seed(owner)


def _seed(owner: str):
    today = datetime.date.today()
    for amount, category, days_ago, note in DEMO_SEED:
        db.execute(
            "INSERT INTO expenses(owner, amount, category, date, note, created_at) "
            "VALUES (?,?,?,?,?,?)",
            (owner, amount, category,
             (today - datetime.timedelta(days=days_ago)).isoformat(), note, db.now_str()))


def merge_guest_into_user(sid: str, user_id: int) -> int:
    """注册时把游客期间记的账带进新账户（种子演示数据除外……全带走也无妨，从简：全带走）"""
    return db.execute("UPDATE expenses SET owner = ? WHERE owner = ?",
                      (f"u_{user_id}", f"g_{sid}"))


def cleanup_old_tenants() -> int:
    """只清游客；注册用户永不清理"""
    cutoff = (datetime.datetime.now() - datetime.timedelta(days=config.TENANT_TTL_DAYS)
              ).strftime("%Y-%m-%d %H:%M:%S")
    stale = db.query("SELECT owner FROM tenants WHERE kind = 'guest' AND last_active < ?",
                     (cutoff,))
    for row in stale:
        db.execute("DELETE FROM expenses WHERE owner = ?", (row["owner"],))
        db.execute("DELETE FROM tenants WHERE owner = ?", (row["owner"],))
    return len(stale)


# ---- 成本护栏：内存计数（重启清零；最坏损失=一天限额）----
_usage = {"date": None, "key": {}, "total": 0}


def check_and_count(ip: str, user_id=None):
    """游客按IP、注册用户按账号。返回 (是否放行, 拒绝原因)"""
    today = datetime.date.today().isoformat()
    if _usage["date"] != today:
        _usage.update({"date": today, "key": {}, "total": 0})
    if _usage["total"] >= config.GLOBAL_DAILY_LIMIT:
        return False, "服务今天的总额度用完了，明天再来吧～（成本护栏在工作）"
    if user_id is not None:
        key, limit = f"u_{user_id}", config.ACCOUNT_DAILY_LIMIT
        tip = f"你今天的额度（{limit}条消息）用完啦，明天再来～"
    else:
        key, limit = f"ip_{ip}", config.IP_DAILY_LIMIT
        tip = (f"游客体验额度（{limit}条/天）用完啦～"
               f"注册用户每天有 {config.ACCOUNT_DAILY_LIMIT} 条哦")
    used = _usage["key"].get(key, 0)
    if used >= limit:
        return False, tip
    _usage["key"][key] = used + 1
    _usage["total"] += 1
    return True, None
