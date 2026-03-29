# 技术负责人 T 当前任务

## 当前阶段

- `LLM V1` 首轮实现已完成，当前已完成真实结果质量复盘并进入下一轮精度优化准备

## 当前唯一目标

- 在不扩范围的前提下，基于已完成的真实样例复盘推进下一轮精度优化整包实现准备

## 当前要看什么

1. `docs/status/summary.md`
2. `docs/comms/inbox-t.md`
3. `docs/tech/v1/llm-v1-implementation-round-2.md`
4. 必要时再读 `docs/tasks/current.md`
5. 需要复盘时再读 `docs/tasks/archive/`

## 当前默认动作

- 保持 V1 极简边界
- 当前代码侧已完成：
- `1. LLM` 配置读取与最小客户端
- `2. LLM` 审查执行器替换
- `3. 结果汇总链路接轨`
- 当前真实联调状态：
- 新配置下 `/models` 可通，极小 `chat/completions` 请求可回包
- 当前已确认新模型需通过 `OPENAI_DISABLE_THINKING=true` 关闭 thinking
- 当前已补 `message.content` / `message.reasoning` 兼容
- `SZCG2025000300-A` 已真实跑到 `completed`
- 当前结果页与下载链路已在真实调用下验证通过
- 当前已完成 `SZCG2025000300-A` 结果质量复盘
- 当前已收口下一轮建议：
- `1. 提示词与规则包联合收口`
- `2. 结果归并轻收口`
- `3. 长条款细切分与重复块降权`
- 平时优先维护本文件，完成一轮实现并准备回提时再更新 `docs/tasks/current.md`
- 当前不继续扩页面、不补零散优化，优先按上述整包进入下一轮精度优化准备
