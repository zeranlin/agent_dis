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
- `implementation-prep-round-2.md`：第二轮实现准备，聚焦解析 worker、规则资产加载器、状态推进和最小测试，并明确当前解析仅为占位实现
- `implementation-prep-round-3.md`：第三轮实现准备，聚焦审查输入装配、规则运行时组装、审查执行最小骨架和中间结果对象落地
- `implementation-prep-round-4.md`：第四轮实现准备，聚焦结果汇总、最终结论生成、Markdown 报告导出与结果对象落地
- `implementation-prep-round-5.md`：第五轮实现准备，聚焦最小 worker 运行入口、运行闭环测试与闭环表述收口
- `implementation-prep-round-6.md`：第六轮实现准备，聚焦结果查询接口、下载接口与报告模板稳定化
- `implementation-prep-round-7.md`：第七轮实现准备，聚焦结果页接入字段明确化、关键错误场景处理与模板后续稳定化
- `implementation-prep-round-8.md`：第八轮实现准备，聚焦结果页最小实现落点、字段消费方式与页面级错误交互
- `implementation-prep-round-9.md`：第九轮实现准备，聚焦结果页信息组织细化、快速操作区与交互反馈补全
- `implementation-prep-round-10.md`：第十轮实现准备，聚焦结果页阅读节奏、动作建议与布局细节优化
- `implementation-prep-round-11.md`：第十一轮实现准备，聚焦结果页文案自然度、状态说明与辅助提示语微调
- `implementation-prep-round-12.md`：第十二轮实现准备，聚焦结果页交付说明、联调提示与页面边界说明
- `implementation-prep-round-13.md`：第十三轮实现准备，聚焦结果页不存在场景的页面级兜底与线程收口判断
- `implementation-prep-round-14.md`：第十四轮实现准备，聚焦解析链路可用化首轮方案、切分块对象与失败分类落地

## 当前规则

- 所有文档默认使用中文
- 技术方案必须追溯到已确认的产品方案
- 不允许脱离 `docs/business/v1/` 单独发明范围
- 先完成主流程技术方案，再进入子流程技术方案
