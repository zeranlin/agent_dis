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
- `implementation-prep-round-15.md`：第十五轮实现准备，聚焦条款误判章节与失败阶段漂移这 2 个最小缺口修复
- `implementation-prep-round-16.md`：第十六轮实现准备，聚焦目录噪声过滤、DOCX 表格文本提取与切分输出衔接优化
- `implementation-prep-round-17.md`：第十七轮实现准备，聚焦 DOCX 表格重复提取这一处最小缺口修复
- `implementation-prep-round-18.md`：第十八轮实现准备，聚焦条款类型与章节上下文向审查输入的稳定传递
- `implementation-prep-round-19.md`：第十九轮实现准备，聚焦最小执行闭环中的上下文解释增强
- `implementation-prep-round-20.md`：第二十轮实现准备，聚焦结果接口与报告输出中的上下文说明一致性
- `implementation-prep-round-21.md`：第二十一轮实现准备，聚焦结果页上下文消费与结果展示口径统一
- `implementation-prep-round-22.md`：第二十二轮实现准备，聚焦下载对象口径统一与结果页快速操作收口
- `implementation-prep-round-23.md`：第二十三轮实现准备，聚焦页面结果对象规范字段保留与技术接口文档收口
- `implementation-prep-round-24.md`：第二十四轮实现准备，聚焦结果页对象定义与消费口径整主题收口
- `implementation-prep-round-25.md`：第二十五轮实现准备，聚焦结果页辅助信息对象化整主题收口
- `implementation-prep-round-26.md`：第二十六轮实现准备，聚焦 V1 收口判断、交付边界确认与交付准备建议
- `implementation-prep-round-27.md`：第二十七轮实现准备，聚焦联调清单、验收入口与交付交接说明
- `implementation-prep-round-28.md`：第二十八轮实现准备，聚焦真实样例联调结果与验收放行判断
- `implementation-prep-round-29.md`：第二十九轮实现准备，按联调记录模板固化真实样例联调与验收记录
- `implementation-prep-round-30.md`：第三十轮实现准备，聚焦验收执行支持、最终交付说明与交接材料清单
- `implementation-prep-round-31.md`：第三十一轮实现准备，聚焦上传页、等待页与结果页的最小页面闭环补齐
- `llm-v1-reduction-plan.md`：`LLM V1` 收缩方案草案，聚焦当前 `LLM` 使用边界收紧、分批执行、最小重试和可验证版本收口
- `overall-reassessment-summary.md`：当前阶段整体再梳理说明，统一收口当前阶段已完成工作、核心问题、整体调整方向与下一步总判断

## 交付准备模板

- `docs/templates/integration-validation-template.md`：联调与验收记录模板

## 当前规则

- 所有文档默认使用中文
- 技术方案必须追溯到已确认的产品方案
- 不允许脱离 `docs/business/v1/` 单独发明范围
- 先完成主流程技术方案，再进入子流程技术方案
