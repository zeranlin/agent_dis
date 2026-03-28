# V1 实现准备第五轮（首版）

## 文档目的

这份文档用于承接结果生成最小骨架成果，收口最小 worker 运行入口与真实运行闭环，确保当前链路不再只是在测试里手动串联，而是能通过明确入口顺序消费队列。

## 1. 产品追溯

本轮实现直接追溯以下已确认文档：

- `docs/status/summary.md`
- `docs/tasks/t-now.md`
- `docs/tasks/current.md`
- `docs/tech/v1/system-design.md`
- `docs/tech/v1/state-machine.md`
- `docs/tech/v1/implementation-prep-round-4.md`

若后续发现运行入口设计与产品边界冲突，应先回提总负责人，不直接扩展调度能力。

## 2. 本轮目标

本轮只服务于一个目标：

把“测试里可串起来的闭环”推进为“系统里有明确入口可运行的最小闭环”。

当前收口内容如下：

1. 最小 worker 运行入口
2. `parse -> review -> aggregate` 顺序消费入口
3. 面向真实运行入口的最小集成测试
4. 文档口径收口，明确区分测试闭环与运行闭环

## 3. 本轮范围

### 3.1 本轮要做

1. 新增统一 worker 入口
2. 支持单轮运行与运行到空闲两种最小模式
3. 让上传后的任务能通过该入口推进到 `completed`
4. 补一条基于运行入口的集成测试
5. 更新任务状态与技术文档中的闭环表述

### 3.2 本轮不做

- 常驻守护进程管理
- 多进程并发调度
- 外部任务编排系统接入
- 结果查询接口
- 下载接口

## 4. 当前实现设计

### 4.1 统一 worker 入口

新增 `app/worker_runner.py`，内部统一串联：

1. `ParseWorker`
2. `ReviewExecutor`
3. `ResultAggregator`

该入口当前提供三种最小运行方式：

- `--once`：执行一轮队列消费
- `--until-idle`：循环执行直到当前队列为空
- 默认持续轮询模式：按间隔不断消费

### 4.2 最小运行命令

当前仓库新增统一命令入口：

```bash
python3 -m app.worker_runner --until-idle
```

并在 `Makefile` 中补充：

```bash
make run-worker
```

该命令当前用于验证系统内部确实存在明确、可执行的最小运行入口。

### 4.3 当前运行闭环口径

当前“运行闭环”指的是：

1. 上传接口写入任务与队列
2. worker 入口消费 `parse`
3. worker 入口消费 `review`
4. worker 入口消费 `result`
5. 任务推进到 `completed`

当前说明：

- 这是最小运行闭环
- 当前仍是单体内顺序消费
- 当前未引入独立调度器、守护进程管理或复杂重试策略

## 5. 状态推进

通过当前 worker 入口，主链路可顺序推进为：

```text
created -> upload_validated -> parsing -> review_queued -> reviewing_clauses -> aggregating -> completed
```

说明：

- 当前运行入口负责把已入队的各阶段任务按顺序继续推进
- 上传接口本身仍只负责创建任务与入队，不直接同步完成整条链路

## 6. 最小测试

本轮新增验证：

1. 上传后不手动逐个调用阶段执行器
2. 只通过 `WorkerRunner.run_until_idle()` 推进任务
3. 最终任务能到达 `completed`
4. 三类队列文件都被消费清空

## 7. 当前结论

实现准备第五轮的目标不是把系统改造成完整后台调度平台，而是补齐一个明确的最小 worker 入口，让仓库中的“结果完成链路”不再只体现在测试拼接上。

完成这一轮后，当前仓库可以被更准确地描述为：

- 已具备最小运行闭环
- 但尚未具备完整结果读取、下载与持续运行治理能力
