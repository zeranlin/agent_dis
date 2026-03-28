# V1 实现准备第二十五轮（首版）

## 文档目的

这份文档用于承接“继续进入下一轮解析链路深化”的最新指令，在不扩范围的前提下按同主题整包回提，完成结果页辅助信息对象化收口。

## 1. 产品追溯

本轮实现直接追溯以下已确认文档：

- `docs/status/summary.md`
- `docs/tasks/t-now.md`
- `docs/tasks/current.md`
- `docs/business/v1/page-and-result-spec.md`
- `docs/tech/v1/data-schema.md`
- `docs/tech/v1/implementation-prep-round-24.md`

## 2. 本轮主题边界

本轮整主题只处理“结果页辅助信息对象化”，不扩到新页面类型、规则能力或复杂交互。

本轮处理范围：

1. 把结果页里的辅助提示文案收回到页面 payload
2. 把结果页里的主要操作按钮收回到页面 payload
3. 让 `completed` / `reviewing` / `failed` 三种页面状态都具备结构化辅助信息
4. 同步技术文档中的页面对象字段定义

## 3. 本轮实现点

### 3.1 页面提示文案对象化

当前页面 payload 统一补齐：

- `page_guidance`
- `support_notes`

这样页面模板不再硬编码主要引导文案，而是消费页面对象中的结构化字段。

### 3.2 页面动作对象化

当前页面 payload 统一补齐：

- `primary_actions`

这样页面主按钮不再散落在模板中拼接，而是由页面对象统一描述。

### 3.3 三种页面状态统一具备辅助展示字段

当前 `completed` / `reviewing` / `failed` 三种状态都统一具备：

- `page_guidance`
- `primary_actions`
- `support_notes`

这样页面对象结构更完整，后续继续扩展或替换展示层时，也更容易复用。

## 4. 最小测试

本轮补齐以下验证：

1. `reviewing` 页面 payload 包含 `page_guidance`
2. `reviewing` 页面 payload 包含 2 个 `primary_actions`
3. `failed` 页面 payload 包含 `page_guidance`
4. `failed` 页面 payload 包含 `support_notes`
5. `completed` 页面 payload 包含 `page_guidance`
6. `completed` 页面 payload 包含 `support_notes`
7. 页面渲染后的文案仍与当前交付面一致
8. 全量 `unittest` 已通过

## 5. 风险与边界

本轮风险可控，原因如下：

- 只调整结果页 payload 和结果页模板消费方式
- 不改解析主链路
- 不改任务状态流转
- 不改规则命中逻辑

本轮明确不做：

- 页面大改版
- 新交互编排系统
- 多页面工作台
- 复杂按钮权限控制

## 6. 当前结论

本轮继续沿着解析链路深化主线推进，并把结果页最后一批明显硬编码的辅助信息收回到了页面对象层。

完成这一轮后：

- 页面 payload 更接近完整 view model
- 页面模板对硬编码提示语和按钮的依赖更少
- 三种页面状态的展示字段更统一
- 当前实现仍保持 V1 极简边界
