# V1 技术文档目录

## 目录目的

这个目录用于存放技术负责人 T 输出的 V1 技术方案文档。

它与 `docs/business/v1/` 的区别是：

- `docs/business/v1/` 负责说明产品为什么这样做、做什么、不做什么
- `docs/tech/v1/` 负责说明技术上怎么做、如何拆、如何落地

## 建议优先补齐的文档

建议技术负责人按以下顺序补齐：

1. `system-design.md`
2. `state-machine.md`
3. `api-spec.md`
4. `data-schema.md`
5. `development-plan.md`
6. `risk-and-assumption.md`

## 当前新增文档

在技术方案首包之后，当前已进入实现准备阶段，并补充：

- `implementation-prep-round-1.md`：第一轮实现准备，聚焦上传接口、任务状态模型、文件解析链路和规则资产加载
- `architecture-layering.md`：V1 技术架构与分层方案，统一说明系统分层、模块边界、关键链路、状态流转和主要风险
- `implementation-prep-round-2.md`：第二轮实现准备，聚焦解析 worker、规则资产加载器、状态推进和最小测试

## 当前规则

- 所有文档默认使用中文
- 技术方案必须追溯到已确认的产品方案
- 不允许脱离 `docs/business/v1/` 单独发明范围
- 先完成主流程技术方案，再进入子流程技术方案
