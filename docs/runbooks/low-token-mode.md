# 低 Token 模式

## 目的

这份文档用于降低多线程协作时的 token 消耗，避免每轮都重复读取长文档、完整任务状态和整份收件箱历史。

## 核心原则

- 先读超短摘要，再读角色短状态
- 先读当前消息，不读历史全文
- 能用提交号和文件名表达，就不要重复贴大段背景
- `current.md` 只保留当前有效状态，不再承载长历史
- 详细历史转入 `docs/tasks/archive/`

## 默认阅读顺序

### 总负责人

1. `docs/status/summary.md`
2. `docs/tasks/owner-now.md`
3. `docs/comms/inbox-owner.md`
4. 必要时再读 `docs/tasks/current.md`

### 产品经理 P

1. `docs/status/summary.md`
2. `docs/tasks/p-now.md`
3. `docs/comms/inbox-p.md`
4. 必要时再读 `docs/tasks/current.md`

### 技术负责人 T

1. `docs/status/summary.md`
2. `docs/tasks/t-now.md`
3. `docs/comms/inbox-t.md`
4. 必要时再读 `docs/tasks/current.md`

## 收件箱使用规则

- 收件箱默认只保留当前唯一有效消息
- 已处理消息立即移入 `docs/comms/archive/`
- 需要复盘历史时，再读取归档文件

## 任务状态使用规则

- `docs/tasks/current.md`：当前有效状态总板
- `docs/tasks/archive/`：历史状态归档目录
- `docs/tasks/owner-now.md`：总负责人短状态
- `docs/tasks/p-now.md`：产品经理 P 短状态
- `docs/tasks/t-now.md`：技术负责人 T 短状态
- `docs/status/summary.md`：全局超短摘要

## 推荐写法

更省 token 的表达方式：

- “基于提交 `c3ee33a` 继续”
- “只读 `docs/comms/inbox-t.md` 最新消息”
- “先读 `docs/status/summary.md`”
- “历史只在需要时读 `docs/comms/archive/`”

不推荐每轮都写：

- 大段历史背景复述
- 全量文档清单
- 重复复制整段任务上下文

## 当前结论

低 token 模式不是减少协作，而是把“默认读长文档”改成“默认读摘要、短状态和当前唯一有效消息”。
