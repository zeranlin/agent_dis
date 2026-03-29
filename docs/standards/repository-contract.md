# 仓库契约

本文定义了人和智能体都应共同遵守的仓库级约束。

## 必需文件

以下文件必须存在：

- `README.md`
- `AGENTS.md`
- `docs/architecture.md`
- `docs/standards/coding.md`
- `docs/standards/agent-quality-rules.md`
- `docs/runbooks/change-checklist.md`
- `docs/templates/task-template.md`
- `docs/tasks/current.md`
- `docs/tasks/backlog.md`
- `docs/tasks/done.md`
- `docs/tasks/template.md`
- `docs/logs/experiments.md`
- `docs/logs/decisions.md`
- `scripts/check-harness.sh`
- `scripts/check-agent-quality.sh`
- `Makefile`
- `.github/pull_request_template.md`

## 仓库不变量

- `AGENTS.md` 必须保持为导航文件，而不是信息堆积区。
- 任何长期有效的工作流变化都应同步更新 `docs/`。
- 新工作必须能在模板、实验日志或决策日志中找到可追溯落点。
- 当前任务状态必须能在 `docs/tasks/` 下找到明确记录。
- 方案讨论和任务拆解必须遵循逐层展开、不跳级的分层规则。
- `make check` 必须保持通过。
- 仓库中的 Markdown 文档默认使用中文编写。
- 仓库文档默认不写本机绝对路径，内部引用优先使用相对路径。
- 对外共享材料如需给出访问入口，优先使用 Git 仓库地址。
- 多线程协作默认优先使用短状态文件和超短摘要，完整状态档案只在必要时读取。
- `LLM` 运行配置只允许通过本地环境变量注入，不得把服务地址、模型名、密钥、密码或其他敏感联调配置写入仓库代码、文档、样例文件或提交记录。
- 如需在仓库中描述 `LLM` 配置，只能记录配置项名称、用途和使用约束，不记录敏感明文值。

## 审阅要求

每次变更都应回答以下问题：

1. 改了什么？
2. 为什么要改？
3. 如何验证？
4. 更新了哪些文档，或者为什么不需要更新文档？
