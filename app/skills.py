"""Skill加载：每次调用都重读文件——改文件=改产品行为，立即生效"""
from . import config


def load_skill(name: str) -> str:
    return (config.SKILLS_DIR / name).read_text(encoding="utf-8")


def valid_categories() -> set:
    """从 categories.md 的"分类体系"一节解析合法分类集合（如 餐饮-正餐）。
    校验集合由Skill文件驱动：用户改文件，安检门的标准跟着变。"""
    cats = set()
    in_section = False
    for line in load_skill("categories.md").splitlines():
        line = line.strip()
        if line.startswith("##"):
            in_section = "分类体系" in line
            continue
        if in_section and line.startswith("-") and "：" in line:
            head, _, rest = line.lstrip("- ").partition("：")
            for sub in rest.split("/"):
                sub = sub.strip()
                if sub:
                    cats.add(f"{head.strip()}-{sub}")
    return cats
