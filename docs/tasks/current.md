# 当前任务

## 当前主题

- 政府采购招标文件合规审查业务方案细化

## 当前角色分工

- 总负责人：统一产品方向、角色协同和最终收口
- 产品经理 P：负责业务方案、产品文档和验收口径
- 技术负责人 T：负责技术方案、接口、状态和开发准备

## 当前目标

- 在现有业务方案基础上，建立 Owner / P / T 协作机制，并推动 V1 进入实现准备阶段

## 当前进展

- 已完成业务方向、核心问题、法规分层、招标文件定位与审查规则体系梳理
- 已完成本体结构图
- 已完成一级审查框架与二级细则清单
- 已补充任务状态层，便于下次继续衔接
- 已细化本体文档中的核心关系定义，开始向数据模型层收敛
- 已形成 V1 产品范围定义草案，统一收敛边界、规则分层、输出结构、角色与流程
- 已形成 V1 默认规则包 1.0 草案，明确默认内置规则集合
- 已形成 V1 字段级数据模型草案，覆盖 8 个核心对象与最小关系链
- 已形成 V1 产品主流程草案，完成主流程层和当前必要二级节点的收口
- 已形成 V1 总体方案草案，统一收敛定位、边界、主流程、子流程、规则和数据支撑
- 已形成 V1 开发交付补充方案草案，补全报告模板、审查执行流程和规则库配置格式
- 已形成 V1 页面与结果对象说明草案，补全极简交互与核心对象样例
- 已形成 V1 固定审查任务指令草案
- 已形成 V1 规则配置样例草案
- 已形成 V1 验收标准草案
- 已形成给技术负责人的开发启动说明
- 已建立 Owner / P / T 角色说明
- 已建立 P 到 T、T 到总负责人的交接规则
- 已建立问题路由对照表
- 已建立三线程日常协作节奏 runbook
- 已建立基于仓库文件和 git 的线程通信机制
- 已补充文档引用路径规范，收口相对路径与 Git 地址使用原则
- 已向技术负责人 T 发出进入实现准备第一轮的正式消息
- 已建立 `docs/tech/v1/` 技术文档目录
- 已形成 `P -> T` 正式交接包，统一收口当前范围、主流程、输入输出对象和验收口径
- 已输出 V1 技术方案首包，覆盖系统设计、状态流转、接口草案、技术数据结构、开发计划与风险假设
- 已输出实现准备第一轮文档，收口上传接口、任务状态模型、文件解析链路和规则资产加载
- 已输出 V1 技术架构与分层方案，统一收口系统分层、模块边界、关键链路、状态流转和主要风险

## 当前结论

- 该业务适合按“规则本体 + 文档结构本体 + 风险本体”三层系统推进
- 产品目标应聚焦于风险点、规则依据、证据定位和整改建议，而不是泛化问答
- V1 采用“报告驱动”模式，审核人员优先查看最终结论/报告，按需下钻证据
- V1 不是规则运营平台，而是带有默认规则包的审查智能体
- V1 主流程当前收敛为：文件进入系统 -> AI 发起审查 -> 生成审查结果 -> 人工查看结果
- V1 总体方案已经具备继续向更细层级拆分的基础
- V1 已具备交给技术负责人开展技术方案和原型设计的主要文档基础
- V1 交互当前收敛为：上传页 -> 审核中状态 -> 结果页
- V1 文档包已进一步补齐到可支撑技术负责人启动开发设计的程度
- 当前仓库已具备支持 3 个独立线程协同推进的基础
- V1 技术侧已形成最小闭环架构基线，可进入实现物和原型开发阶段
- V1 实现准备第一轮范围已明确，可按四个最小实现物直接拆分开发
- V1 架构分层与模块边界已进一步明确，可作为开发前总览基线

## 当前任务列表

### 总负责人

- 统一审阅 P 与 T 的后续产出
- 决定技术方案是否通过并进入开发阶段

### 产品经理 P

- 维护 `docs/business/v1/` 的产品方案一致性
- 配合技术负责人补充实现所需的产品侧说明
- 在交接后只处理 T 回提的产品边界澄清，不替代技术方案设计

### 技术负责人 T

- 在 `docs/tech/v1/` 下输出第一版技术方案
- 优先补齐系统设计、状态流转、接口草案和开发计划
- 基于技术方案首包继续落实现物优先级和最小测试方案
- 输出实现准备第一轮文档，支撑上传接口、状态模型、解析链路和规则资产加载开工
- 输出技术架构与分层方案，作为开发前总览架构基线

## 下一步建议

- 由技术负责人 T 基于架构分层方案和实现准备第一轮文档继续进入最小实现物落地，优先编码上传接口、任务模型、解析 worker 和规则加载器

## 阻塞或待确认

- 实现准备第一轮文档已完成，下一阶段待补充默认规则包实现物、固定任务指令实现物与最小测试方案

## 当前交接主题

- V1 审查智能体最小闭环交接包

## 交接给 T 的内容

- 已确认 V1 只覆盖公开招标、货物与服务、单文件、招标文件正文场景
- 已确认主流程为：文件进入系统 -> AI 发起审查 -> 生成审查结果 -> 人工查看结果
- 已确认主查看层输出为：最终结论、审查报告
- 已确认支撑层输出为：风险点、规则依据、证据片段、整改建议
- 已确认当前人工动作闭环到查看和下载结果，不纳入在线审批流转
- 已补充正式交接文档：`docs/business/v1/p-to-t-handoff-v1.md`

## T 下一步要做什么

- 基于技术方案首包开始实现准备
- 优先落地上传接口、任务状态模型、文件解析链路和规则资产加载
- 基于实现准备第一轮文档拆解最小实现任务并进入编码
- 若发现产品范围冲突，回提总负责人确认，不自行改写产品边界

## 关联文档

- `docs/roles/owner.md`
- `docs/roles/product-manager-p.md`
- `docs/roles/tech-lead-t.md`
- `docs/runbooks/handoff-p-to-t.md`
- `docs/runbooks/handoff-t-to-owner.md`
- `docs/runbooks/question-routing.md`
- `docs/runbooks/daily-collaboration-rhythm.md`
- `docs/comms/README.md`
- `docs/comms/inbox-owner.md`
- `docs/comms/inbox-p.md`
- `docs/comms/inbox-t.md`
- `docs/comms/template.md`
- `docs/business/government-procurement-compliance-overview.md`
- `docs/business/government-procurement-compliance-ontology.md`
- `docs/business/government-procurement-review-framework.md`
- `docs/business/v1/product-scope.md`
- `docs/business/v1/default-rule-pack.md`
- `docs/business/v1/data-model.md`
- `docs/business/v1/main-flow.md`
- `docs/business/v1/overall-solution.md`
- `docs/business/v1/delivery-extension.md`
- `docs/business/v1/page-and-result-spec.md`
- `docs/business/v1/review-task-instruction.md`
- `docs/business/v1/rule-config-examples.md`
- `docs/business/v1/acceptance-criteria.md`
- `docs/business/v1/tech-lead-kickoff.md`
- `docs/business/v1/p-to-t-handoff-v1.md`
- `docs/tech/v1/README.md`
- `docs/tech/v1/system-design.md`
- `docs/tech/v1/state-machine.md`
- `docs/tech/v1/api-spec.md`
- `docs/tech/v1/data-schema.md`
- `docs/tech/v1/development-plan.md`
- `docs/tech/v1/risk-and-assumption.md`
- `docs/tech/v1/implementation-prep-round-1.md`
- `docs/tech/v1/architecture-layering.md`
