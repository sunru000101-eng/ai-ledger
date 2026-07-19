# 💰 AI记账助手（ai-ledger）

对话式AI记账：**说一句话，就记好账**。两天 vibe coding 完成的面试Demo，同时是作者自用的真实产品。

> "早上瑞幸19，中午外卖35" → 自动拆两笔、归类、入账
> "这个月吃饭花了多少？" → 真实查询，绝不编数
> "生成这个月的消费报告" → 300字人话报告

## 快速开始

```bash
bash verify.sh   # 首次：自动装环境 + 验证模型Key（先在 .env 里配置）
bash run.sh      # 启动服务
# 浏览器打开 http://127.0.0.1:8000
```

模型使用任意 OpenAI 兼容接口（DeepSeek/Kimi/智谱/通义），在 `.env` 三行配置。

## 架构

```
浏览器（聊天 + 账本视图 + Agent日志抽屉）
        │ HTTP
FastAPI 后端
        ├── Agent循环（≤6轮）──→ 大模型（OpenAI兼容接口）
        │      ├── 权限管线：增/查/报告放行，删/改需确认
        │      ├── PreToolUse 钩子：schema校验（安检门）
        │      ├── PostToolUse 钩子：结构化日志（摄像头）
        │      └── 错误恢复三层：API重试 / 带原因让模型改 / 反问用户
        ├── 5个工具（dispatch map）：记账/查账/删/改/月报
        ├── skills/ 可编辑技能文件（改文件=改产品行为，即时生效）
        │      ├── categories.md   分类规则（常驻注入）
        │      └── report_style.md 报告模板（按需注入）
        └── SQLite 本地账本（数据不出本机）
```

Harness 完整图谱20个环节中**选9砍11**，每个决策的理由见 [docs/design.md](docs/design.md) §3.9。

## 质量

| 验证 | 结果 | 重跑命令 |
|---|---|---|
| 评测集（20条真实口语，5类含坑题） | **20/20 = 100%** | `.venv/bin/python eval/run_eval.py` |
| 验收清单（11项功能与安全） | **11/11 通过** | `.venv/bin/python tests/acceptance.py` |
| 离线冒烟（19项Harness部件） | **19/19 通过** | `.venv/bin/python tests/smoke.py` |

评测历程：基线95% → 定位边界案例（"人均80"被过度保守拒记）→ 精修一条提示词规则 → 单次重跑出现随机噪声（90%）→ 关键题3次重复验证区分波动与回归 → 全量100%。评测集同时是**回归测试**：任何提示词/Skill改动后重跑，防止改崩。

## 项目结构

```
app/          后端（agent.py 是心脏）
web/          前端（单文件，零外部依赖）
skills/       技能文件（用户可直接编辑）
eval/         评测集 + 跑分脚本 + 报告
tests/        冒烟 / 在线链路 / 验收
docs/         设计文档 / 产品化战略 / 复盘 / 演示脚本
cli.py        终端版（开发调试用）
```

## 文档索引

- [design.md](docs/design.md) —— 产品设计（含Harness八件装备、20选9决策表）
- [strategy.md](docs/strategy.md) —— 产品化战略（差异化四层堆叠）
- [reflection.md](docs/reflection.md) —— 复盘（目标漂移的教训）
- [demo_script.md](docs/demo_script.md) —— 5分钟面试演示脚本 + 追问预案
- [eval/results.md](eval/results.md) —— 最新评测报告（自动生成）

## 刻意不做

多用户登录（伪需求）、预算提醒（错的阶段）、语音输入与App端（高成本低边际收益）、部署上云（演示用不上+数据不该出去）。每条理由详见设计文档 §1。
