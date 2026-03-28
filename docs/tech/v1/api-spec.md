# V1 接口草案（首版）

## 文档目的

这份文档用于定义 V1 最小可开发链路所需的接口草案，统一上传、状态查询、结果查询和下载接口的职责与对象结构。

## 1. 设计原则

- 先满足单文件、单任务闭环
- 接口对象与 `docs/business/v1/page-and-result-spec.md` 保持一致
- 上传和审查执行解耦，使用异步任务模式
- 页面优先读取稳定对象，不暴露内部审查细节

## 2. 接口总览

| 接口 | 方法 | 用途 |
| --- | --- | --- |
| `/api/v1/review-tasks` | `POST` | 上传文件并创建任务 |
| `/api/v1/review-tasks/{task_id}` | `GET` | 查询任务当前状态 |
| `/api/v1/review-tasks/{task_id}/result` | `GET` | 查询审查结果 |
| `/api/v1/review-tasks/{task_id}/downloads/{file_type}` | `GET` | 下载结果文件 |

## 3. 创建审查任务

### 3.1 请求

- 方法：`POST`
- 路径：`/api/v1/review-tasks`
- Content-Type：`multipart/form-data`

请求字段：

| 字段 | 类型 | 是否必填 | 说明 |
| --- | --- | --- | --- |
| `file` | binary | 是 | 招标文件原始文件 |

### 3.2 成功响应

状态码：`201`

```json
{
  "task_id": "task_001",
  "file_name": "招标文件.pdf",
  "file_type": "PDF",
  "status": "uploaded",
  "message": "文件已成功上传，系统即将开始审核。"
}
```

### 3.3 失败响应

状态码建议：

- `400`：文件为空或字段缺失
- `415`：文件格式不支持
- `422`：文件校验不通过

失败对象：

```json
{
  "error_code": "UNSUPPORTED_FILE_TYPE",
  "error_message": "仅支持 PDF 或 Word 文件。"
}
```

## 4. 查询任务状态

### 4.1 请求

- 方法：`GET`
- 路径：`/api/v1/review-tasks/{task_id}`

### 4.2 成功响应

状态码：`200`

```json
{
  "task_id": "task_001",
  "status": "reviewing",
  "file_name": "招标文件.pdf",
  "started_at": "2026-03-28T18:30:00+08:00",
  "message": "系统正在自动审核，请稍候。"
}
```

### 4.3 失败态响应

当任务失败时仍返回 `200`，由状态字段表达业务失败：

```json
{
  "task_id": "task_001",
  "status": "failed",
  "file_name": "招标文件.pdf",
  "started_at": "2026-03-28T18:30:00+08:00",
  "message": "文件解析失败，请重新提交文件。"
}
```

### 4.4 异常响应

- `404`：任务不存在

## 5. 查询审查结果

### 5.1 请求

- 方法：`GET`
- 路径：`/api/v1/review-tasks/{task_id}/result`

### 5.2 可用条件

- 任务状态为 `completed`

若任务未完成，建议返回 `409`：

```json
{
  "error_code": "RESULT_NOT_READY",
  "error_message": "审查结果尚未生成完成。"
}
```

### 5.3 成功响应

状态码：`200`

```json
{
  "task_id": "task_001",
  "status": "completed",
  "file_name": "招标文件.pdf",
  "summary_title": "审查已完成",
  "overall_conclusion": "本文件存在明显风险，建议重点关注资格条件和评分规则。",
  "report_markdown": "# 审查报告\n\n## 总体结论\n\n本文件存在明显风险。\n",
  "downloadable_files": [
    {
      "name": "最终结论.md",
      "type": "conclusion_markdown",
      "url": "/api/v1/review-tasks/task_001/downloads/conclusion"
    },
    {
      "name": "审查报告.md",
      "type": "report_markdown",
      "url": "/api/v1/review-tasks/task_001/downloads/report"
    }
  ]
}
```

### 5.4 扩展字段建议

在不影响主查看层的前提下，结果对象可补充：

- `risk_count_summary`
- `top_risks`
- `risk_items`

当前最小代码实现已补充：

- `conclusion_markdown`
- `risk_count_summary`
- `top_risks`
- `generated_at`

这些字段应作为可选扩展，不应阻塞 V1 首版交付。

## 6. 下载结果文件

### 6.1 请求

- 方法：`GET`
- 路径：`/api/v1/review-tasks/{task_id}/downloads/{file_type}`

### 6.2 `file_type` 取值

- `conclusion`
- `report`

### 6.3 成功响应

- 状态码：`200`
- 响应头：`Content-Type: text/markdown; charset=utf-8`

### 6.4 失败响应

- `404`：任务不存在或文件不存在
- `409`：结果尚未就绪

当前最小代码实现进一步区分：

- `409 RESULT_NOT_READY`
- `409 RESULT_FAILED`
- `404 DOWNLOAD_NOT_FOUND`

## 7. 内外对象映射

| 页面对象 | 接口来源 |
| --- | --- |
| 上传结果对象 | `POST /api/v1/review-tasks` |
| 审核状态对象 | `GET /api/v1/review-tasks/{task_id}` |
| 审查结果对象 | `GET /api/v1/review-tasks/{task_id}/result` |

当前最小代码实现另外补充了一个结果页验证入口：

- `GET /review-tasks/{task_id}/page`

该入口用于服务端渲染最小结果页，验证字段消费和页面级错误交互，不替代正式 API。

当前结果对象还补充页面接入辅助字段：

- `page_url`
- `status_api_url`
- `result_api_url`

## 8. 版本控制建议

- 路径统一带 `v1`
- V1 内部字段可增量扩展，但不应删除已对外承诺字段
- 若未来引入任务列表、人工复核或多文件联审，应新增接口而非破坏现有主链路接口

## 9. 验证方式

1. 上传后是否返回唯一 `task_id`
2. 审核中页面是否只依赖状态查询接口即可展示
3. 结果页是否只依赖结果接口即可展示
4. 下载按钮是否能直接使用结果对象中的下载地址

## 10. 当前结论

V1 接口先收敛为 1 个创建接口、2 个查询接口和 1 个下载接口，足够支撑极简页面闭环，也便于后续继续扩展任务列表和人工复核能力。

当前最小代码实现已补齐：

- 结果查询接口
- 报告下载接口
- 结论下载接口

并保持与 `review_result` 对象和 `downloadable_files` 字段映射一致。
