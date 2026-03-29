# LLM V1 首轮实现回提

## 文档目的

本文件用于记录 `LLM V1` 首轮实现的实际落地情况、验证结果和当前阻塞，作为本轮正式技术结论。

## 本轮范围

本轮严格按 `docs/tech/v1/llm-v1-implementation-kickoff.md` 执行，只做以下事项：

1. 接入真实 `LLM` 配置读取
2. 用真实 `LLM` 调用替换关键词占位执行器
3. 让最小结构化风险结果接入现有结果汇总、结果页和下载链路
4. 以 `SZCG2025000300-A` 作为首个真实联调样例验证

## 已完成实现

### 1. 已落最小 `LLM` 客户端

当前已新增 `app/llm_client.py`，实现以下能力：

- 通过环境变量读取 `OPENAI_BASE_URL`、`OPENAI_API_KEY`、`OPENAI_MODEL`
- 支持 `OPENAI_TIMEOUT_SECONDS`
- 支持 `OPENAI_REVIEW_BATCH_SIZE`
- 支持 `OPENAI_REVIEW_CLAUSE_MAX_CHARS`
- 支持 `OPENAI_MAX_COMPLETION_TOKENS`
- 支持 `OPENAI_REASONING_EFFORT`
- 按 OpenAI 风格 `chat/completions` 发起请求
- 对配置缺失、网关异常、超时和返回结构错误做显式报错

### 2. 已替换审查执行主路径

当前 `app/review_executor.py` 已不再走 `KEYWORD_MAP` 关键词命中主路径，已改为：

1. 从 `ReviewInputAssembler` 读取条款、规则包和固定任务指令
2. 按批次组装条款审查输入
3. 调用真实 `LLM`
4. 解析最小结构化结果
5. 落地现有 `risk` / `evidence` 中间对象
6. 继续推进到现有结果汇总链路

### 3. 已定义最小结构化输出映射

当前发送给 `LLM` 的最小输出字段为：

- `clause_id`
- `rule_code`
- `risk_title`
- `risk_level`
- `risk_category`
- `evidence_text`
- `review_reasoning`
- `need_human_confirm`

当前映射策略如下：

- `risk_title` 优先使用模型输出，缺省回退到规则名
- `risk_level` 优先使用模型输出，缺省回退到规则默认级别
- `risk_category` 和 `need_human_confirm` 当前收入口径说明中，不额外扩数据表结构
- `evidence_text` 直接进入现有证据对象
- `review_reasoning` 保留章节上下文、片段类型、规则编码和人工确认建议，继续兼容现有结果页展示

### 4. 已保持现有结果链路不变

当前结果汇总、结果页和 Markdown 下载链路未重做，继续复用：

- `app/result_aggregator.py`
- `app/result_presenter.py`
- `app/upload_service.py`

这保证了本轮改动集中在执行层，不扩页面和下载链路范围。

### 5. 已补自动化测试隔离层

当前测试中已新增本地假的 OpenAI 风格服务，用于验证：

- 执行器确实走 HTTP `LLM` 调用路径
- 结构化返回可被解析
- 风险、证据、结果页和下载链路仍可正常工作

## 验证结果

## 2026-03-29 基线检查

- `make check` 通过
- `python3 -m unittest discover -s tests -p 'test_*.py'` 通过
- 共 `36` 个测试通过

## 2026-03-29 本地假服务联调

结论：`通过`

说明：

- 本地假 OpenAI 风格服务下，`LLM -> 风险对象 -> 结果对象 -> 页面/下载` 链路已打通
- 审查执行器不再依赖关键词占位命中作为主路径

## 2026-03-29 真实外部服务连通验证

结论：`部分通过`

已验证通过：

- `OPENAI_BASE_URL` 对应的 `/models` 接口可正常返回 `200`
- 模型列表中可见 `gpt-5.4`、`gpt-5.4-mini`、`gpt-5.2`

未验证通过：

- 极小 `chat/completions` 请求在 `gpt-5.4-mini`、`gpt-5.2`、`gpt-5.4` 下均超时
- 极小 `responses` 请求同样超时
- `SZCG2025000300-A` 真实样例在当前环境下进入上传和解析成功，但在审查执行阶段失败

真实样例表现如下：

- 样例：`SZCG2025000300-A`
- 上传：成功
- 解析：成功
- 结构切分：成功
- 审查执行：失败
- 失败码：`REVIEW_EXECUTION_FAILED`
- 失败原因：外部 `LLM` 推理请求超时或网关返回 `504 Gateway Time-out`

## 当前判断

当前需要把“代码实现状态”和“真实环境打通状态”分开判断。

### 代码实现状态

判断：`已完成首轮最小实现`

原因：

- 真实 `LLM` 配置读取已落
- 真实 HTTP 调用路径已落
- 结构化结果映射已落
- 现有结果页和下载链路已接轨
- 自动化测试已覆盖主路径

### 真实环境打通状态

判断：`未打通`

原因：

- 真实推理接口在极小请求下也不可用
- 当前阻塞不在仓库执行链路，而在外部推理服务可用性

## 当前阻塞

本轮唯一阻塞为：

`真实 LLM 推理服务当前不可用，导致 SZCG2025000300-A 无法完成真实端到端联调。`

当前阻塞不建议由技术线程自行拍板规避，因为这会涉及：

- 是否更换联调用模型
- 是否切换网关或服务地址
- 是否接受先以轻模型完成验收联调

## 当前建议

建议总负责人在以下方向中拍板其一：

1. 保持当前模型与网关配置不变，等待推理服务恢复后继续真实联调
2. 允许联调阶段临时切到当前网关下可稳定返回的更轻模型，再继续推进 `LLM V1`
3. 提供新的可用推理网关后，技术线程继续按当前实现直接联调

## 本轮正式结论

本轮正式结论为：

`代码实现已完成 LLM V1 首轮最小替换，但真实外部推理服务未打通，因此当前不能判定为“真实 LLM 审查闭环已完成”。`
