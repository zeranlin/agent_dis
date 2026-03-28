# V1 规则配置样例（草案）

## 文档目的

这份文档用于给技术负责人提供一版可直接落地的规则配置参考样式。

目标不是一次定义复杂规则引擎，而是先把 V1 默认规则包中的规则，沉淀成统一、可维护、可升级的配置结构。

## 1. 配置定位

V1 的规则配置主要服务于三件事：

1. 让默认规则包可被程序加载
2. 让智能体拿到稳定的规则元数据
3. 让输出结果可以回溯到具体规则

因此，V1 规则配置优先追求：

- 结构清晰
- 字段统一
- 人可读
- 便于版本升级

## 2. 推荐配置结构

每条规则建议至少包含以下六组信息：

1. 规则标识信息
2. 规则分类信息
3. 适用范围信息
4. 审查目标信息
5. 输出映射信息
6. 版本升级信息

## 3. 字段总表

| 字段 | 字段说明 |
| --- | --- |
| `rule_id` | 规则唯一标识 |
| `rule_code` | 规则编号 |
| `rule_name` | 规则名称 |
| `rule_domain` | 一级规则域 |
| `rule_subtype` | 二级细则名称 |
| `file_module` | 主要适用文件模块 |
| `procurement_method` | 适用采购方式 |
| `procurement_type` | 适用采购类型 |
| `execution_level` | 执行级别 |
| `risk_level` | 默认风险等级 |
| `target_description` | 审查目标描述 |
| `trigger_description` | 触发逻辑描述 |
| `positive_signals` | 典型命中信号 |
| `evidence_requirement` | 需要抽取的证据要求 |
| `output_focus` | 输出重点 |
| `basis_summary` | 规则依据摘要 |
| `status` | 规则状态 |
| `version` | 规则版本 |
| `updated_at` | 最近更新时间 |

## 4. 推荐配置样式

V1 可以优先采用 `YAML` 作为规则配置落地格式。

原因：

- 适合人读
- 适合版本管理
- 适合后续程序加载

## 5. 样例一：R1 地域限制检查

```yaml
rule_id: rule_v1_r1
rule_code: R1
rule_name: 地域限制检查
rule_domain: 公平竞争规则
rule_subtype: 资格条件限制
file_module:
  - 资格条件
  - 商务要求
procurement_method:
  - 公开招标
procurement_type:
  - 货物
  - 服务
execution_level: 自动判定
risk_level: 高
target_description: 识别对供应商设置不当地域限制的表述
trigger_description: 发现本地注册、本地办公、本地团队、本地业绩等限制性要求时触发
positive_signals:
  - 本地注册
  - 本地办公
  - 常驻本地
  - 本地业绩
evidence_requirement: 抽取包含地域限制表述的原文及其位置标签
output_focus: 输出限制性表述、命中位置和风险说明
basis_summary: 招标文件不应以地域条件不当限制供应商参与竞争
status: 启用
version: 1.0.0
updated_at: 2026-03-28
```

## 6. 样例二：R9 评分项未量化检查

```yaml
rule_id: rule_v1_r9
rule_code: R9
rule_name: 评分项未量化检查
rule_domain: 评审可解释性规则
rule_subtype: 评分标准量化
file_module:
  - 评分办法
procurement_method:
  - 公开招标
procurement_type:
  - 货物
  - 服务
execution_level: 自动判定
risk_level: 高
target_description: 识别评分标准中主观表述较多且缺乏量化依据的条款
trigger_description: 出现优良中差、综合评价、酌情打分等表述且未给出明确量化标准时触发
positive_signals:
  - 优良中差
  - 综合评价
  - 酌情打分
  - 评委比较
evidence_requirement: 抽取评分项原文、对应分值和位置标签
output_focus: 输出未量化评分项、分值信息和风险说明
basis_summary: 评分标准应明确、量化、可执行，避免过度主观裁量
status: 启用
version: 1.0.0
updated_at: 2026-03-28
```

## 7. 程序加载建议

技术实现时，建议把规则配置加载分成两层：

1. 规则元数据层
2. 审查执行层

其中：

- 规则元数据层用于展示、回溯和结果归类
- 审查执行层用于组装进智能体输入

V1 不建议一开始就做复杂表达式引擎。

更稳妥的做法是：

- 先由规则配置提供统一审查框架
- 再由固定审查任务指令约束智能体如何使用这些规则

## 8. 当前结论

V1 规则配置样例的核心价值，在于把“默认规则包文档”进一步推进到“可程序落地的配置结构”。

技术负责人可据此直接开始设计：

- 规则配置文件
- 规则加载模块
- 规则到输出的映射逻辑
