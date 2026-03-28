# V1 实现准备第四轮（首版）

## 文档目的

这份文档用于承接审查输入装配与执行骨架成果，收口结果汇总、最终结论生成与 Markdown 报告导出的最小实现方案，确保 V1 主链路首次完整推进到 `completed`。

## 1. 产品追溯

本轮实现直接追溯以下已确认文档：

- `docs/status/summary.md`
- `docs/tasks/current.md`
- `docs/business/v1/page-and-result-spec.md`
- `docs/business/v1/acceptance-criteria.md`
- `docs/tech/v1/system-design.md`
- `docs/tech/v1/state-machine.md`
- `docs/tech/v1/data-schema.md`
- `docs/tech/v1/implementation-prep-round-3.md`

若后续发现结果对象、导出物或状态定义与上述文档冲突，应先回提总负责人，不直接改写产品边界。

## 2. 本轮目标

本轮目标只有一个：

让当前最小链路从 `aggregating` 继续推进到 `completed`。

为此，本轮只收口以下内容：

1. 结果汇总模块
2. 最终结论生成
3. Markdown 报告导出
4. 结果对象持久化
5. 对应状态推进与最小测试

## 3. 本轮范围

### 3.1 本轮要做

1. 从 `risk_item`、`evidence_item` 汇总出统一 `review_result`
2. 生成面向审核人员查看的 `overall_conclusion`
3. 生成标准 Markdown 审查报告与最终结论文档
4. 为结果对象补齐导出文件路径
5. 将任务状态推进到 `completed`
6. 补齐从上传到结果完成的最小链路测试

### 3.2 本轮不做

- 结果查询接口扩展
- 下载接口扩展
- 风险去重与复杂归并
- 更细颗粒度整改建议生成
- 富文本报告样式优化

## 4. 当前实现设计

### 4.1 结果汇总模块

新增 `ResultAggregator`，负责消费 `queues/result/` 中的待处理任务。

处理步骤如下：

1. 读取任务
2. 读取该任务下的风险点与证据片段
3. 统计高、中、低风险数量
4. 生成最终结论文本
5. 生成 Markdown 最终结论与 Markdown 审查报告
6. 持久化 `review_result`
7. 将任务推进到 `completed`

### 4.2 最终结论生成口径

当前最终结论使用最小规则汇总口径：

- 若存在高风险，则输出“存在高风险问题，建议优先复核”
- 若无高风险但有中风险，则输出“建议进一步人工复核”
- 若仅有低风险，则输出“当前仅识别到低风险提示”
- 若未识别到风险，则输出“建议结合人工复核继续确认”

该口径当前只用于支撑结果闭环，不等同于最终产品态的复杂结论生成策略。

### 4.3 结果对象

本轮正式落地 `review_result`，当前至少包含：

- `result_id`
- `task_id`
- `project_id`
- `document_id`
- `status`
- `summary_title`
- `overall_conclusion`
- `report_markdown`
- `conclusion_markdown`
- `risk_count_high`
- `risk_count_medium`
- `risk_count_low`
- `report_file_path`
- `conclusion_file_path`
- `generated_at`

### 4.4 Markdown 导出

当前导出两类文件：

1. 最终结论 Markdown
2. 审查报告 Markdown

当前保存位置为：

- `outputs/conclusions/`
- `outputs/reports/`

当前报告结构采用最小模板，包含：

- 文件信息
- 总体结论
- 风险明细
- 每条风险对应的证据片段

## 5. 状态推进

本轮新增状态推进链路如下：

```text
aggregating -> completed
```

说明：

- `aggregating` 表示中间结果已具备，待汇总器生成最终产物
- `completed` 表示最终结论、审查报告和结果对象均已落地

若结果汇总失败，则任务进入：

- `failed`
- `RESULT_AGGREGATION_FAILED`

## 6. 当前落地对象与存储

### 6.1 新增持久化对象

- `review_result`

### 6.2 新增队列

- `queues/result/`

### 6.3 新增输出目录

- `outputs/reports/`
- `outputs/conclusions/`

### 6.4 元数据文件

- `metadata/results.json`

## 7. 最小测试

本轮至少覆盖以下验证：

1. 审查执行完成后能够投递结果汇总任务
2. 结果汇总器能消费结果队列
3. 能生成 `review_result`
4. 能生成两份 Markdown 文件
5. 任务状态能推进到 `completed`

## 8. 当前结论

实现准备第四轮的目标不是把结果页和下载接口全部做完，而是把“结果汇总、最终结论、Markdown 报告导出”收口成最小闭环。

只要这一轮完成，V1 当前仓库就首次具备从上传到结果完成的完整最小链路，后续即可继续补结果查询、下载接口和更稳定的结果模板。
