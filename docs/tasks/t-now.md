# 技术负责人 T 当前任务

## 当前阶段

- `LLM V1` 首轮实现阶段

## 当前唯一目标

- 用真实 `LLM` 调用替换当前关键词占位执行层，打通 `LLM V1` 最小可用审查闭环

## 当前要看什么

1. `docs/status/summary.md`
2. `docs/comms/inbox-t.md`
3. `docs/tech/v1/llm-v1-implementation-kickoff.md`
4. 必要时再读 `docs/tasks/current.md`
5. 需要复盘时再读 `docs/tasks/archive/`

## 当前默认动作

- 保持 V1 极简边界
- 当前已结束待命支持状态，正式切回 `LLM` 主线实现
- 已确认当前页面闭环、解析链路、结果页和下载链路可继续沿用
- 当前开发重点不是继续扩页面，而是替换审查执行层
- 当前优先顺序固定为：
- `1. LLM` 连接配置与最小调用打通
- `2. LLM` 审查执行器落地
- `3. 结果汇总链路接轨`
- `4. 最小端到端联调`
- 平时优先维护本文件，完成一轮实现并准备回提时再更新 `docs/tasks/current.md`
- 如无新的阻塞问题，不继续补零散页面或交付项
