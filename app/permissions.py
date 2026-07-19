"""权限管线：增/查/报告自动放行（高频低风险），删/改需用户确认（低频不可逆）。
未注册的工具默认要确认——安全默认值。"""
PERMISSION_RULES = {
    "add_expense": "allow",
    "query_expenses": "allow",
    "generate_report": "allow",
    "delete_expense": "ask",
    "update_expense": "ask",
}


def check(tool_name: str) -> str:
    return PERMISSION_RULES.get(tool_name, "ask")
