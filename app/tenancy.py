"""演示模式的多租户与成本护栏。
- 每个访客（cookie sid）一本独立 SQLite 账，互不可见
- 新访客自动种入几笔演示数据，打开就能看到账本长什么样
- 成本护栏：每IP日限额 + 全站日限额（内存计数，重启清零，够演示场景用）
- 过期清理：租户数据文件超过 TTL 天未活跃即删除
"""
import datetime
import time

from . import config, db, tools

# 新访客的演示种子数据：(金额, 分类, 几天前, 备注)
DEMO_SEED = [
    (19, "餐饮-饮品", 0, "瑞幸咖啡"),
    (42, "餐饮-正餐", 0, "麻辣烫"),
    (28, "交通-打车", 1, "打车回家"),
    (128, "娱乐-游戏", 3, "Switch游戏"),
    (89, "日用-日用品", 5, "超市采购"),
]


def activate(sid: str):
    """把当前请求绑定到某个访客的独立账本（在中间件里调用）"""
    db.TENANT_ID.set(sid)
    path = config.TENANTS_DIR / f"{sid}.db"
    fresh = not path.exists()
    db.DB_PATH_OVERRIDE.set(path)
    if fresh:
        db.init_db()
        _seed()
    else:
        path.touch()  # 刷新活跃时间，供 TTL 清理判断


def _seed():
    today = datetime.date.today()
    for amount, category, days_ago, note in DEMO_SEED:
        tools.TOOL_HANDLERS["add_expense"]({
            "amount": amount,
            "category": category,
            "date": (today - datetime.timedelta(days=days_ago)).isoformat(),
            "note": note,
        })


def cleanup_old_tenants() -> int:
    if not config.TENANTS_DIR.exists():
        return 0
    cutoff = time.time() - config.TENANT_TTL_DAYS * 86400
    removed = 0
    for f in config.TENANTS_DIR.glob("*.db"):
        if f.stat().st_mtime < cutoff:
            f.unlink(missing_ok=True)
            removed += 1
    return removed


# ---- 成本护栏：内存计数（重启清零；最坏损失=一天限额，可接受）----
_usage = {"date": None, "ip": {}, "total": 0}


def check_and_count(ip: str):
    """返回 (是否放行, 拒绝原因)。放行时消耗一条额度。"""
    today = datetime.date.today().isoformat()
    if _usage["date"] != today:
        _usage.update({"date": today, "ip": {}, "total": 0})
    if _usage["total"] >= config.GLOBAL_DAILY_LIMIT:
        return False, "演示站今天的总额度用完了，明天再来吧～（这是成本护栏在工作）"
    used = _usage["ip"].get(ip, 0)
    if used >= config.IP_DAILY_LIMIT:
        return False, f"你今天的体验额度（{config.IP_DAILY_LIMIT}条消息）用完啦，明天再来～"
    _usage["ip"][ip] = used + 1
    _usage["total"] += 1
    return True, None
