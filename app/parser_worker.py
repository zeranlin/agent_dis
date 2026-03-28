from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from app.document_parser import ParseFailure, parse_document
from app.models import build_block_record, build_chapter_record, build_clause_record
from app.repository import JsonRepository


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

            parsed_document_payload = parse_document(Path(document.source_uri))
            parsed_document = document.with_updates(
                raw_text=parsed_document_payload.raw_text,
                parsed_status="parsed",
                page_count=parsed_document_payload.page_count,
            )
            self.repository.save_document(parsed_document)

            section_id_mapping: dict[str, str] = {}
            chapter_payloads: dict[str, dict[str, object]] = {}
            clause_count = 0
            section_count = 0

            for block in parsed_document_payload.blocks:
                self.repository.save_block(
                    build_block_record(
                        block_id=block.block_id,
                        document_id=document.document_id,
                        block_type=block.block_type,
                        title=block.title,
                        text=block.text,
                        source_page_start=block.source_page_start,
                        source_page_end=block.source_page_end,
                        order_index=block.order_index,
                        parent_block_id=block.parent_block_id,
                        source_anchor=block.source_anchor,
                    )
                )

                if block.block_type == "section":
                    section_count += 1
                    chapter_id = f"chapter_{uuid4().hex[:12]}"
                    section_id_mapping[block.block_id] = chapter_id
                    chapter_payloads[chapter_id] = {
                        "chapter_title": block.title,
                        "chapter_order": block.order_index,
                        "text_lines": [block.title],
                    }
                    continue

                parent_chapter_id = section_id_mapping.get(block.parent_block_id or "")
                if parent_chapter_id is None:
                    if not section_id_mapping:
                        fallback_chapter_id = f"chapter_{uuid4().hex[:12]}"
                        section_id_mapping["default"] = fallback_chapter_id
                        chapter_payloads[fallback_chapter_id] = {
                            "chapter_title": "默认章节",
                            "chapter_order": 1,
                            "text_lines": [],
                        }
                    parent_chapter_id = next(iter(section_id_mapping.values()))

                chapter_payload = chapter_payloads[parent_chapter_id]
                chapter_payload["text_lines"].append(block.text)
                clause_count += 1
                chapter_title = str(chapter_payload["chapter_title"])
                location_anchor = block.source_anchor or block.title or f"片段{block.order_index}"
                self.repository.save_clause(
                    build_clause_record(
                        clause_id=f"clause_{uuid4().hex[:12]}",
                        document_id=document.document_id,
                        chapter_id=parent_chapter_id,
                        clause_order=block.order_index,
                        clause_text=block.text,
                        location_label=f"{chapter_title} / {location_anchor}",
                    )
                )

            for chapter_id, chapter_payload in chapter_payloads.items():
                chapter_text = "\n".join(
                    str(line).strip() for line in chapter_payload["text_lines"] if str(line).strip()
                )
                self.repository.save_chapter(
                    build_chapter_record(
                        chapter_id=chapter_id,
                        document_id=document.document_id,
                        chapter_title=str(chapter_payload["chapter_title"]),
                        chapter_order=int(chapter_payload["chapter_order"]),
                        chapter_text=chapter_text,
                    )
                )

            task.transition_to(
                "parsed",
                f"文件解析完成，已生成 {section_count} 个章节块和 {clause_count} 个可审查片段。",
            )
            self.repository.save_task(task)
            task.transition_to("review_queued", "文件解析完成，系统即将开始规则审查。")
            self.repository.save_task(task)
            self.repository.enqueue_review_job(task)
        except ParseFailure as exc:
            self.repository.save_document(document.with_updates(parsed_status="failed"))
            task.mark_failed(
                error_code=exc.error_code,
                error_message=exc.detail_message,
                status_message=exc.user_message,
            )
            self.repository.save_task(task)
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
