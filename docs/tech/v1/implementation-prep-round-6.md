# V1 实现准备第六轮（首版）

## 文档目的

这份文档用于承接最小运行闭环成果，收口结果查询接口、下载接口和 Markdown 报告模板稳定化方案，确保审核人员已可通过接口读取最终结论并下载结果文件。

## 1. 产品追溯

本轮实现直接追溯以下已确认文档：

- `docs/status/summary.md`
- `docs/tasks/t-now.md`
- `docs/tasks/current.md`
- `docs/business/v1/page-and-result-spec.md`
- `docs/business/v1/acceptance-criteria.md`
- `docs/tech/v1/api-spec.md`
- `docs/tech/v1/implementation-prep-round-5.md`

若后续发现结果读取能力与已确认页面边界冲突，应先回提总负责人，不直接扩展前端或权限范围。

## 2. 本轮目标

本轮只服务于三个目标：

1. 为已完成任务提供结果查询接口
2. 为结果文件提供最小下载能力
3. 把报告模板从占位格式整理为更稳定的结构

## 3. 本轮范围

### 3.1 本轮要做

1. 新增结果查询接口
2. 新增结果下载接口
3. 建立 `review_result -> 接口响应对象` 映射
4. 收口 Markdown 结论模板与报告模板结构
5. 补齐接口级最小测试

### 3.2 本轮不做

- 结果页前端实现
- 权限控制
- 富文本或 PDF 导出
- 复杂模板美化
- 风险分组、排序和去重优化

## 4. 当前实现设计

### 4.1 结果查询接口

当前新增：

- `GET /api/v1/review-tasks/{task_id}/result`

行为约束如下：

- 任务不存在时返回 `404`
- 任务未完成时返回 `409`
- 任务已完成时返回结果对象

### 4.2 下载接口

当前新增：

- `GET /api/v1/review-tasks/{task_id}/downloads/report`
- `GET /api/v1/review-tasks/{task_id}/downloads/conclusion`

行为约束如下：

- 仅允许下载已完成任务的文件
- 返回 `text/markdown; charset=utf-8`
- 通过 `Content-Disposition` 提供最小附件下载能力

### 4.3 结果对象映射

当前接口返回对象由 `ReviewResultRecord` 映射而来，最小字段包括：

- `task_id`
- `status`
- `file_name`
- `summary_title`
- `overall_conclusion`
- `report_markdown`
- `downloadable_files`

其中 `downloadable_files` 当前固定提供两类下载项：

- 最终结论 Markdown
- 审查报告 Markdown

### 4.4 报告模板稳定化

本轮对 Markdown 模板做最小整理：

最终结论当前结构包括：

- 文件概览
- 结论摘要
- 风险统计
- 处理建议

审查报告当前结构包括：

- 文件信息
- 总体结论
- 报告说明
- 风险明细

当前说明：

- 模板目标是稳定可读、便于接口输出
- 当前不是最终视觉版报告模板
- 当前不引入复杂排版和样式系统

## 5. 最小测试

本轮至少覆盖以下验证：

1. 任务完成后可通过结果接口读取结果对象
2. 结果对象中包含下载地址
3. 可分别下载报告与结论文档
4. 任务未完成时结果接口返回 `409`
5. 下载文件内容符合当前模板结构

## 6. 当前结论

实现准备第六轮的目标不是把结果交付层全部做完，而是先把“读取结果、下载结果、稳定模板”这三件事做成可验证的最小接口闭环。

完成这一轮后，当前仓库已具备：

- 上传与状态查询
- worker 运行闭环
- 结果读取接口
- Markdown 下载能力

后续可继续补更稳的模板组织、结果页接入和更完整的错误处理。
