# V1 实现准备第二轮（首版）

## 文档目的

这份文档用于承接实现准备第一轮成果，收口第二轮需要直接落地的输入链路实现物，重点覆盖解析 worker、规则资产加载器、状态推进和最小测试。

## 1. 本轮目标

本轮目标是把当前链路真正推进到：

`upload_validated -> parsing -> parsed`

为此，本轮只聚焦两类实现：

1. 解析 worker
2. 规则资产加载器

## 2. 本轮范围

### 2.1 本轮要做

1. 解析任务消费方式
2. `PDF` / `Word` 解析器最小实现
3. `procurement_document`、`document_chapter`、`document_clause` 的最小落地
4. 默认规则包和固定任务指令的资产目录与加载器
5. 对应状态推进与最小测试

### 2.2 本轮不做

- 风险识别执行器细化
- 结果汇总实现
- 页面层扩展
- 外部存储替换

## 3. 当前实现设计

### 3.1 解析任务消费方式

- 上传接口继续将任务写入 `queues/parse/`
- 解析 worker 扫描并消费待处理任务
- 单个任务消费成功后删除队列文件

### 3.2 解析器最小实现

- `PDF` 与 `Word` 当前都先统一走“文件读取 -> 文本解码 -> 结构切分”的最小实现
- 优先支持 UTF-8 和 `gb18030`
- 首版不追求复杂版面还原，只保证稳定提取 `raw_text`

### 3.3 结构落地

本轮新增最小落地对象：

- `document_chapter`
- `document_clause`

当前以 JSON 文件形式写入 `metadata/chapters.json` 和 `metadata/clauses.json`。

### 3.4 规则资产加载

本轮新增资产目录：

```text
assets/
  review/
    rule-packs/
      default-rule-pack.v1.yaml
    prompts/
      review-task-instruction.v1.md
```

加载器负责：

- 加载 12 条默认规则
- 校验必要字段
- 加载固定审查任务指令文本

## 4. 状态推进

解析 worker 当前负责推进以下状态：

1. `upload_validated`
2. `parsing`
3. `parsed`

若解析失败，则写入：

- `failed`
- `DOCUMENT_PARSE_FAILED`

## 5. 最小测试

本轮至少覆盖：

1. 解析 worker 能消费队列并生成章节、条款
2. 任务状态能推进到 `parsed`
3. 规则资产加载器能加载 12 条规则和固定任务指令

## 6. 当前结论

实现准备第二轮的目标不是把审查链路全部做完，而是把输入链路真正跑通。只要解析 worker 和规则资产加载器稳定落地，下一轮就可以进入审查输入装配和审查执行实现。
