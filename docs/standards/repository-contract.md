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

## 审阅要求

每次变更都应回答以下问题：

1. 改了什么？
2. 为什么要改？
3. 如何验证？
4. 更新了哪些文档，或者为什么不需要更新文档？
