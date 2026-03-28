# V1 实现准备第三轮（首版）

## 文档目的

这份文档用于承接前两轮输入链路成果，收口“审查输入装配 + 审查执行最小骨架”的当前实现方案，确保 V1 已具备进入结果汇总阶段前的稳定中间产物。

## 1. 产品追溯

本轮实现直接追溯以下已确认文档：

- `docs/tasks/current.md`
- `docs/business/v1/main-flow.md`
- `docs/business/v1/data-model.md`
- `docs/business/v1/review-task-instruction.md`
- `docs/business/v1/acceptance-criteria.md`
- `docs/tech/v1/system-design.md`
- `docs/tech/v1/state-machine.md`
- `docs/tech/v1/implementation-prep-round-2.md`

若后续实现发现与上述文档冲突，应先回提总负责人，不直接扩展产品边界。

## 2. 本轮目标

本轮只服务于一个目标：

让链路从 `review_queued` 继续推进到“已生成可汇总的中间审查结果”。

当前收口内容如下：

1. 审查输入装配器
2. 规则包与固定任务指令的运行时装配
3. 审查执行最小占位实现
4. 风险点、证据片段、风险说明的最小 schema
5. 为下一轮结果汇总准备可消费的中间对象

## 3. 本轮范围

### 3.1 本轮要做

1. 从 `document_clause` 读取条款，组装运行时审查输入
2. 读取默认规则包和固定审查任务指令，形成统一输入对象
3. 落地最小审查执行器，消费 `queues/review/`
4. 持久化 `risk_item` 与 `evidence_item` 中间对象
5. 把任务状态推进到 `aggregating`
6. 补齐装配与执行测试

### 3.2 本轮不做

- 最终结论生成
- 审查报告 Markdown 汇总
- 结果下载接口
- 复杂规则调优
- 真实 LLM 联调

## 4. 当前实现设计

### 4.1 审查输入装配器

新增 `ReviewInputAssembler`，负责按任务维度装配运行时输入：

- `task`
- `document`
- `clauses`
- `rules`
- `prompt_text`
- `output_schema`

装配器职责是把“解析结果 + 规则资产”转成执行器稳定可消费的单一对象，不在装配阶段做风险判断。

### 4.2 运行时输入对象

当前运行时输入对象使用 `ReviewRuntimeInput`，包含：

- `task_id`
- `document_id`
- `file_name`
- `prompt_text`
- `rules`
- `clauses`
- `output_schema`

其目标不是覆盖未来所有执行参数，而是先固定住本轮执行骨架的最小输入面。

### 4.3 最小输出 schema

当前最小输出 schema 分为两组字段：

1. 风险点字段
2. 证据片段字段

风险点字段当前至少包括：

- `risk_id`
- `rule_code`
- `rule_name`
- `risk_level`
- `execution_level`
- `location_label`
- `risk_description`
- `review_reasoning`

证据片段字段当前至少包括：

- `evidence_id`
- `quoted_text`
- `location_label`
- `evidence_note`

这些字段用于保证下一轮结果汇总阶段可以直接消费，而不需要重新回查执行器内部临时变量。

### 4.4 审查执行最小骨架

新增 `ReviewExecutor`，当前执行方式为：

1. 扫描 `queues/review/`
2. 将任务推进到 `reviewing_clauses`
3. 调用装配器读取运行时输入
4. 基于规则编号做最小关键词命中
5. 生成 `risk_item` 和 `evidence_item`
6. 将任务推进到 `aggregating`

当前实现说明：

- 它是“最小可跑通的执行骨架”
- 当前不是正式语义审查能力
- 当前不是 LLM 判定实现
- 当前只用于打通审查阶段状态、对象和测试基线

### 4.5 当前占位判定口径

本轮仅对少量规则提供关键词命中占位：

- `R1`：地域限制相关关键词
- `R5`：品牌型号指向相关关键词
- `R9`：评分项未量化相关关键词

该口径只用于验证：

- 审查任务可以被执行
- 风险对象可以落地
- 证据对象可以追溯到原文条款

不应被理解为 V1 已完成正式规则审查能力。

## 5. 状态推进

本轮新增状态推进链路如下：

```text
parsed -> review_queued -> reviewing_clauses -> aggregating
```

说明：

- `parsed -> review_queued` 由解析 worker 完成
- `review_queued -> reviewing_clauses -> aggregating` 由审查执行器完成
- `aggregating` 当前表示“中间审查结果已具备，待下一轮汇总模块接手”

若执行失败，则任务进入：

- `failed`
- `REVIEW_EXECUTION_FAILED`

## 6. 当前落地对象

本轮新增或正式启用的对象如下：

### 6.1 审查运行时对象

- `ReviewRuntimeInput`

### 6.2 中间结果对象

- `RiskItemRecord`
- `EvidenceItemRecord`

### 6.3 存储位置

当前继续采用本地 JSON 文件持久化：

- `metadata/risks.json`
- `metadata/evidences.json`
- `queues/review/`

## 7. 最小测试

本轮至少覆盖以下验证：

1. 解析完成后能够进入 `review_queued` 并投递审查任务
2. 审查输入装配器能组装规则、指令、条款和输出 schema
3. 审查执行器能消费审查队列
4. 审查执行器能持久化风险点与证据片段
5. 任务状态能推进到 `aggregating`

## 8. 当前结论

实现准备第三轮的目标不是完成最终结果交付，而是把审查阶段的“输入装配、执行占位、中间对象落地”收口为稳定基线。

只要这一轮完成，下一轮就可以聚焦结果汇总、最终结论生成和报告导出，而不必再回头重做审查阶段输入结构。
