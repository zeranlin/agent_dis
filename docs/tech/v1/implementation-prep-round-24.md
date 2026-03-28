# V1 实现准备第二十四轮（首版）

## 文档目的

这份文档用于承接“继续进入下一轮解析链路深化”的最新指令，在不扩范围的前提下按同主题整包回提，完成结果页对象定义与消费口径收口。

## 1. 产品追溯

本轮实现直接追溯以下已确认文档：

- `docs/status/summary.md`
- `docs/tasks/t-now.md`
- `docs/tasks/current.md`
- `docs/business/v1/page-and-result-spec.md`
- `docs/business/v1/acceptance-criteria.md`
- `docs/tech/v1/api-spec.md`
- `docs/tech/v1/data-schema.md`
- `docs/tech/v1/implementation-prep-round-23.md`

## 2. 本轮主题边界

本轮整主题只处理“结果页对象定义与消费口径收口”，不跨到解析能力、规则能力或页面大改版。

本轮处理范围：

1. 结果页 payload 组装逻辑统一收口
2. 三种页面状态的规范字段保留一致化
3. 页面消费层与结果对象字段语义进一步统一
4. 技术文档中的页面对象与结果对象映射补齐

本轮明确不做：

- OCR
- 多文件
- 新页面类型
- 复杂工作台
- 新规则能力

## 3. 本轮实现点

### 3.1 页面 payload 统一由 helper 生成

当前新增统一的页面 payload 组装 helper，覆盖：

- `completed`
- `reviewing`
- `failed`

这样页面对象的生成不再散落在 `UploadService` 中，后续如果继续补字段或调整口径，可以在同一入口统一处理。

### 3.2 三种页面状态统一保留规范字段

当前三种页面状态都会稳定保留：

- `summary_title`
- `overall_conclusion`

同时继续保留：

- `title`
- `message`

作为当前模板兼容字段。

### 3.3 页面模板优先消费规范字段

当前页面模板优先使用：

- `summary_title`
- `overall_conclusion`

仅在缺失时才退回：

- `title`
- `message`

这样结果页模板对结果对象的依赖关系更清晰，也更接近正式结果对象的语义。

### 3.4 技术文档补齐页面对象映射

当前技术文档同步补齐：

- 页面 payload 的规范字段
- 页面 payload 与结果对象、任务对象的映射关系
- 结果对象样例与当前实现的关系说明

## 4. 最小测试

本轮补齐以下验证：

1. `reviewing` 页面 payload 保留 `summary_title`
2. `reviewing` 页面 payload 保留 `overall_conclusion`
3. `failed` 页面 payload 保留 `summary_title`
4. `failed` 页面 payload 保留 `overall_conclusion`
5. `completed` 页面 payload 保留 `summary_title`
6. `completed` 页面 payload 保留 `overall_conclusion`
7. 三种页面状态当前都保持规范字段与兼容字段一致
8. 全量 `unittest` 已通过

## 5. 风险与边界

本轮风险可控，原因如下：

- 只调整页面 payload 组装和页面消费口径
- 不改解析主链路
- 不改任务状态流转语义
- 不改规则命中逻辑

当前剩余兼容项：

- `title`
- `message`

这两个字段当前仍保留，用于避免一次性移除旧消费口径带来的回归风险。

## 6. 当前结论

本轮继续沿着解析链路深化主线推进，但本次已不是零散补点，而是把“结果页对象定义与消费口径”作为一个完整主题做了收口。

完成这一轮后：

- 页面 payload 生成入口更统一
- 页面对象与结果对象语义更一致
- 三种页面状态字段口径更稳定
- 技术文档与当前实现更一致
- 当前实现仍保持 V1 极简边界
