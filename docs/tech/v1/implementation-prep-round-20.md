# V1 实现准备第二十轮（首版）

## 文档目的

这份文档用于承接“继续进入下一轮解析链路深化”的最新指令，在不扩范围的前提下补齐结果接口与报告输出中的上下文说明一致性。

## 1. 产品追溯

本轮实现直接追溯以下已确认文档：

- `docs/status/summary.md`
- `docs/tasks/t-now.md`
- `docs/tasks/current.md`
- `docs/business/v1/parsing-and-segmentation-minimum.md`
- `docs/business/v1/page-and-result-spec.md`
- `docs/tech/v1/implementation-prep-round-19.md`

## 2. 本轮目标

本轮只处理两件事：

1. 让结果接口中的重点风险继续保留章节上下文与片段类型
2. 让 Markdown 审查报告中的风险明细与中间结果说明保持一致

## 3. 本轮实现点

### 3.1 结果接口补齐上下文字段

当前 `UploadService.get_review_result()` 中的 `top_risks` 补齐以下字段：

- `chapter_title`
- `clause_type`
- `review_reasoning`

这样结果页或后续消费方读取重点风险时，不必再只依赖 `location_label` 做二次猜测，可以直接看到章节上下文、片段类型和审查说明。

### 3.2 报告风险明细补齐上下文说明

当前 `ResultAggregator.build_report_markdown()` 中的风险明细补齐以下展示项：

- `章节上下文`
- `片段类型`

这样“解析输出 -> 审查输入 -> 风险中间结果 -> 最终报告”这条说明链在最终产物上保持一致，人工复核时也更容易对照命中位置理解风险来源。

### 3.3 结果消费口径保持 V1 极简

本轮没有新增规则能力，也没有扩展解析范围，仅做现有上下文字段的稳定透传与结果展示收口。

明确不做：

- OCR
- 多文件合并
- 复杂表格结构恢复
- 复杂版式还原
- 新增平台化结果编排

## 4. 最小测试

本轮补齐以下验证：

1. 结果接口的 `top_risks` 包含 `chapter_title`
2. 结果接口的 `top_risks` 包含 `clause_type`
3. 结果接口的 `top_risks` 包含 `review_reasoning`
4. 审查报告 Markdown 包含“章节上下文”
5. 审查报告 Markdown 包含“片段类型”

## 5. 当前结论

本轮继续沿着解析链路深化主线推进，但只补“结果可读性和说明一致性”这一处最小缺口。

完成这一轮后：

- 结果接口中的重点风险信息更完整
- 下载报告与中间结果说明口径更一致
- “解析 -> 执行 -> 结果”的解释链进一步收齐
- 当前实现仍保持 V1 极简边界
