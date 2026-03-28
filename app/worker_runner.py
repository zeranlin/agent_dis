from __future__ import annotations

import argparse
import time
from pathlib import Path

from app.parser_worker import ParseWorker
from app.repository import JsonRepository
from app.result_aggregator import ResultAggregator
from app.review_executor import ReviewExecutor
from app.server import build_runtime_root


class WorkerRunner:
    def __init__(self, repository: JsonRepository, root_dir: Path):
        self.repository = repository
        self.root_dir = root_dir
        self.parse_worker = ParseWorker(repository)
        self.review_executor = ReviewExecutor(repository, root_dir)
        self.result_aggregator = ResultAggregator(repository, root_dir)

    def run_once(self) -> dict[str, int]:
        parse_count = self.parse_worker.run_pending_jobs()
        review_count = self.review_executor.run_pending_jobs()
        result_count = self.result_aggregator.run_pending_jobs()
        return {
            "parse_jobs": parse_count,
            "review_jobs": review_count,
            "result_jobs": result_count,
        }

    def run_until_idle(self, max_rounds: int = 10) -> dict[str, int]:
        totals = {
            "parse_jobs": 0,
            "review_jobs": 0,
            "result_jobs": 0,
            "rounds": 0,
        }
        for _ in range(max_rounds):
            round_result = self.run_once()
            totals["parse_jobs"] += round_result["parse_jobs"]
            totals["review_jobs"] += round_result["review_jobs"]
            totals["result_jobs"] += round_result["result_jobs"]
            totals["rounds"] += 1
            if sum(round_result.values()) == 0:
                break
        return totals


def build_worker_runner(root_dir: Path | None = None) -> WorkerRunner:
    runtime_root = root_dir or build_runtime_root()
    repository = JsonRepository(runtime_root)
    return WorkerRunner(repository, runtime_root)


def main() -> None:
    parser = argparse.ArgumentParser(description="V1 审查任务最小 worker 运行入口")
    parser.add_argument("--once", action="store_true", help="只执行一轮 parse/review/result 消费")
    parser.add_argument("--until-idle", action="store_true", help="循环执行直到当前队列为空")
    parser.add_argument("--max-rounds", type=int, default=10, help="until-idle 模式下的最大轮次")
    parser.add_argument("--poll-seconds", type=float, default=2.0, help="持续运行模式下的轮询间隔秒数")
    args = parser.parse_args()

    runner = build_worker_runner()

    if args.once:
        result = runner.run_once()
        print(result)
        return

    if args.until_idle:
        result = runner.run_until_idle(max_rounds=args.max_rounds)
        print(result)
        return

    while True:
        result = runner.run_once()
        print(result)
        time.sleep(args.poll_seconds)


if __name__ == "__main__":
    main()
