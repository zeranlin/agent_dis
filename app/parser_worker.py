from __future__ import annotations

import re
from pathlib import Path
from uuid import uuid4

from app.models import build_chapter_record, build_clause_record
from app.repository import JsonRepository


CHAPTER_PATTERN = re.compile(r"^(第[一二三四五六七八九十百]+章.*|\d+(?:\.\d+)*[、.].*)$")
CLAUSE_PATTERN = re.compile(r"^(\d+(?:\.\d+){0,3}[、.]?.*|第[一二三四五六七八九十]+条.*)$")


class ParseWorker:
    def __init__(self, repository: JsonRepository):
        self.repository = repository

    def run_pending_jobs(self) -> int:
        processed_count = 0
        for job_path in self.repository.list_parse_jobs():
            self._process_job(job_path)
            processed_count += 1
        return processed_count

    def _process_job(self, job_path: Path) -> None:
        job = self.repository.read_parse_job(job_path)
        task = self.repository.get_task(str(job["task_id"]))
        document = self.repository.get_document(str(job["document_id"]))
        if task is None or document is None:
            self.repository.delete_parse_job(job_path)
            return

        try:
            task.transition_to("parsing", "系统正在解析文件结构。")
            self.repository.save_task(task)

            raw_text = self._extract_text(Path(document.source_uri))
            page_count = max(1, raw_text.count("\f") + 1)
            chapter_segments = split_chapters(raw_text)
            parsed_document = document.with_updates(
                raw_text=raw_text,
                parsed_status="parsed",
                page_count=page_count,
            )
            self.repository.save_document(parsed_document)

            clause_count = 0
            for chapter_order, chapter_segment in enumerate(chapter_segments, start=1):
                chapter_id = f"chapter_{uuid4().hex[:12]}"
                chapter_record = build_chapter_record(
                    chapter_id=chapter_id,
                    document_id=document.document_id,
                    chapter_title=chapter_segment["title"],
                    chapter_order=chapter_order,
                    chapter_text=chapter_segment["text"],
                )
                self.repository.save_chapter(chapter_record)

                clauses = split_clauses(chapter_segment["text"])
                for clause_order, clause_text in enumerate(clauses, start=1):
                    clause_count += 1
                    self.repository.save_clause(
                        build_clause_record(
                            clause_id=f"clause_{uuid4().hex[:12]}",
                            document_id=document.document_id,
                            chapter_id=chapter_id,
                            clause_order=clause_order,
                            clause_text=clause_text,
                            location_label=f"{chapter_record.chapter_title}-条款{clause_order}",
                        )
                    )

            task.transition_to("parsed", f"文件解析完成，已生成 {len(chapter_segments)} 个章节和 {clause_count} 个条款。")
            self.repository.save_task(task)
            task.transition_to("review_queued", "文件解析完成，系统即将开始规则审查。")
            self.repository.save_task(task)
            self.repository.enqueue_review_job(task)
        except Exception as exc:
            self.repository.save_document(document.with_updates(parsed_status="failed"))
            task.mark_failed(
                error_code="DOCUMENT_PARSE_FAILED",
                error_message=str(exc),
                status_message="文件解析失败，请重新提交文件。",
            )
            self.repository.save_task(task)
        finally:
            self.repository.delete_parse_job(job_path)

    @staticmethod
    def _extract_text(path: Path) -> str:
        # 当前仅提供最小文本解码占位实现，还不等同于真实 PDF/Word 提取能力。
        content = path.read_bytes()
        for encoding in ("utf-8", "gb18030"):
            try:
                return content.decode(encoding)
            except UnicodeDecodeError:
                continue
        return content.decode("utf-8", errors="ignore")


def split_chapters(raw_text: str) -> list[dict[str, str]]:
    stripped_lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
    if not stripped_lines:
        return [{"title": "默认章节", "text": ""}]

    chapters: list[dict[str, str]] = []
    current_title = "默认章节"
    current_lines: list[str] = []

    for line in stripped_lines:
        if CHAPTER_PATTERN.match(line):
            if current_lines:
                chapters.append({"title": current_title, "text": "\n".join(current_lines)})
            current_title = line
            current_lines = []
            continue
        current_lines.append(line)

    if current_lines or not chapters:
        chapters.append({"title": current_title, "text": "\n".join(current_lines)})

    return chapters


def split_clauses(chapter_text: str) -> list[str]:
    stripped_lines = [line.strip() for line in chapter_text.splitlines() if line.strip()]
    if not stripped_lines:
        return [""]

    clauses: list[str] = []
    current_lines: list[str] = []

    for line in stripped_lines:
        if CLAUSE_PATTERN.match(line) and current_lines:
            clauses.append("\n".join(current_lines))
            current_lines = [line]
            continue
        current_lines.append(line)

    if current_lines:
        clauses.append("\n".join(current_lines))

    return clauses
