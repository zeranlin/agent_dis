# agent_dis

这是一个受 OpenAI“harness engineering”理念启发的智能体优先仓库脚手架。

这个仓库的目标，是让人在以智能体为主的增量开发过程中，始终共享同一份事实来源：

- `AGENTS.md` 是智能体的顶层导航文件。
- `docs/` 用来存放应当长期保留在仓库中的知识。
- `docs/templates/` 定义任务接入模板。
- `docs/logs/` 记录实验和决策过程。
- `scripts/check-harness.sh` 用来校验仓库最小契约。
- `scripts/check-agent-quality.sh` 用来校验智能体产出质量评估规则。
- `Makefile` 提供统一的本地检查入口。

## 快速开始

```bash
make check
```

## 仓库结构

- `AGENTS.md`：智能体导航与工作约定
- `docs/architecture.md`：系统边界与预期结构
- `docs/templates/`：新任务模板
- `docs/logs/`：实验与决策记录
- `docs/standards/`：编码与仓库约束
- `docs/runbooks/`：可复用的工作流与变更清单
- `.github/`：Pull Request 模板

## 工作原则

我们的目标不是把所有说明都塞进一个文件，而是：

1. 让仓库成为事实来源。
2. 让 `AGENTS.md` 保持简短、以导航为主。
3. 尽可能把重要规则编码进脚本和检查流程。
4. 优先采用小而可审阅、验证步骤明确的变更。

## 当前重点

`agent_dis` 当前阶段的重点，是先建立一套可持续运转的智能体交付脚手架：

- 在实现扩张之前先澄清产品边界
- 标准化任务接入与验证方式
- 把实验结果和架构决策沉淀在仓库内
- 让智能体产出质量可见、可检查
