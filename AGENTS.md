# AGENTS.md

这个文件是智能体在本仓库内工作的统一入口。

## 从这里开始

开始修改前，请按顺序阅读以下文件：

1. `README.md`
2. `docs/architecture.md`
3. `docs/standards/repository-contract.md`
4. `docs/standards/agent-quality-rules.md`
5. `docs/tasks/current.md`
6. `docs/runbooks/change-checklist.md`

然后执行：

```bash
make check
```

## 工作规则

- 把这个仓库视为事实记录系统。
- 长期有效的决策要写进 `docs/`，不要只留在聊天或 PR 评论里。
- 保持改动尽量小，便于审阅。
- 如果引入新的工作流或新约束，要同时补文档和自动化检查。
- 当文档与代码发生漂移时，尽量在同一次变更里修正。
- 仓库内文档默认使用相对路径，不写本机绝对路径；对外共享时优先使用 Git 仓库地址。
- `LLM` 配置只能通过本地环境变量使用，不把服务地址、模型名、密钥或密码明文写入仓库。

## 知识存放位置

- 架构与边界：`docs/architecture.md`
- 仓库约束：`docs/standards/repository-contract.md`
- 编码规范：`docs/standards/coding.md`
- 智能体质量评估规则：`docs/standards/agent-quality-rules.md`
- 任务模板：`docs/templates/task-template.md`
- 当前任务：`docs/tasks/current.md`
- 待办池：`docs/tasks/backlog.md`
- 已完成任务：`docs/tasks/done.md`
- 任务状态模板：`docs/tasks/template.md`
- 实验记录：`docs/logs/experiments.md`
- 决策记录：`docs/logs/decisions.md`
- 变更工作流：`docs/runbooks/change-checklist.md`

## 完成定义

满足以下条件后，任务才算完成：

1. 相关文档仍然准确。
2. `make check` 通过。
3. 验证步骤已经写入变更说明或 PR。
4. 如果新工作改变了行为、方向或认知，必须在对应模板或日志中留下明确记录。
