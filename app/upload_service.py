from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from app.models import build_document_record, build_review_task
from app.result_presenter import build_top_risk_payload, sort_risks_for_display
from app.repository import JsonRepository


SUPPORTED_TYPES = {
    ".pdf": "PDF",
    ".doc": "Word",
    ".docx": "Word",
}


class UploadValidationError(Exception):
    def __init__(self, status_code: int, error_code: str, error_message: str):
        super().__init__(error_message)
        self.status_code = status_code
        self.error_code = error_code
        self.error_message = error_message

    def to_response(self) -> tuple[int, dict[str, str]]:
        return self.status_code, {
            "error_code": self.error_code,
            "error_message": self.error_message,
        }


class UploadProcessingError(Exception):
    def __init__(self, error_code: str, error_message: str):
        super().__init__(error_message)
        self.error_code = error_code
        self.error_message = error_message

    def to_response(self) -> tuple[int, dict[str, str]]:
        return 500, {
            "error_code": self.error_code,
            "error_message": self.error_message,
        }


class ResultAccessError(Exception):
    def __init__(self, status_code: int, error_code: str, error_message: str):
        super().__init__(error_message)
        self.status_code = status_code
        self.error_code = error_code
        self.error_message = error_message

    def to_response(self) -> tuple[int, dict[str, str]]:
        return self.status_code, {
            "error_code": self.error_code,
            "error_message": self.error_message,
        }


@dataclass
class UploadFile:
    filename: str
    content: bytes


class UploadService:
    def __init__(self, repository: JsonRepository):
        self.repository = repository

    def create_review_task(self, upload_file: UploadFile) -> dict[str, str]:
        file_type = self._validate_upload(upload_file)
        task_id = f"task_{uuid4().hex[:12]}"
        project_id = f"project_{uuid4().hex[:12]}"
        document_id = f"document_{uuid4().hex[:12]}"

        task = build_review_task(
            task_id=task_id,
            project_id=project_id,
            document_id=document_id,
            file_name=upload_file.filename,
            file_type=file_type,
        )
        self.repository.save_task(task)

        try:
            stored_path = self.repository.save_upload(task_id, upload_file.filename, upload_file.content)
            document = build_document_record(
                document_id=document_id,
                project_id=project_id,
                file_name=upload_file.filename,
                file_type=file_type,
                source_uri=str(stored_path),
            )
            self.repository.save_document(document)
            task.transition_to("upload_validated", "文件已成功上传，系统即将开始审核。")
            self.repository.save_task(task)
            self.repository.enqueue_parse_job(task)
            return task.to_upload_response()
        except Exception as exc:
            task.mark_failed(
                error_code="UPLOAD_PERSIST_FAILED",
                error_message=str(exc),
                status_message="文件落地失败，任务已终止，请重新提交。",
            )
            self.repository.save_task(task)
            raise UploadProcessingError("UPLOAD_PERSIST_FAILED", "文件落地失败，请重新提交。") from exc

    def get_review_task_status(self, task_id: str) -> dict[str, str | None] | None:
        task = self.repository.get_task(task_id)
        if task is None:
            return None
        return task.to_status_response()

    def get_review_result(self, task_id: str) -> dict[str, object]:
        task = self.repository.get_task(task_id)
        if task is None:
            raise ResultAccessError(404, "TASK_NOT_FOUND", "任务不存在。")
        if task.internal_status == "failed":
            raise ResultAccessError(409, "RESULT_FAILED", task.status_message)
        if task.internal_status != "completed":
            raise ResultAccessError(409, "RESULT_NOT_READY", "审查结果尚未生成完成。")

        result = self.repository.get_result_by_task(task_id)
        if result is None:
            raise ResultAccessError(404, "RESULT_NOT_FOUND", "审查结果不存在。")
        risks = self.repository.list_risks_by_task(task_id)
        top_risks = [build_top_risk_payload(risk) for risk in sort_risks_for_display(risks)[:3]]
        return result.to_result_response(file_name=task.file_name, top_risks=top_risks)

    def download_result_file(self, task_id: str, file_type: str) -> tuple[str, str, str]:
        task = self.repository.get_task(task_id)
        if task is None:
            raise ResultAccessError(404, "TASK_NOT_FOUND", "任务不存在。")
        if task.internal_status == "failed":
            raise ResultAccessError(409, "RESULT_FAILED", task.status_message)
        if task.internal_status != "completed":
            raise ResultAccessError(409, "RESULT_NOT_READY", "审查结果尚未生成完成。")

        if file_type == "report":
            content = self.repository.read_report_markdown(task_id)
            if content is None:
                raise ResultAccessError(404, "FILE_NOT_FOUND", "审查报告文件不存在。")
            return "审查报告.md", "text/markdown; charset=utf-8", content
        if file_type == "conclusion":
            content = self.repository.read_conclusion_markdown(task_id)
            if content is None:
                raise ResultAccessError(404, "FILE_NOT_FOUND", "最终结论文件不存在。")
            return "最终结论.md", "text/markdown; charset=utf-8", content
        raise ResultAccessError(404, "DOWNLOAD_NOT_FOUND", "下载类型不存在。")

    def get_result_page_payload(self, task_id: str) -> dict[str, object]:
        task = self.repository.get_task(task_id)
        if task is None:
            raise ResultAccessError(404, "TASK_NOT_FOUND", "任务不存在。")

        if task.internal_status == "completed":
            result_payload = self.get_review_result(task_id)
            return {
                "page_state": "completed",
                "status_label": "结果已生成",
                "summary_title": str(result_payload["summary_title"]),
                "overall_conclusion": str(result_payload["overall_conclusion"]),
                "title": str(result_payload["summary_title"]),
                "file_name": task.file_name,
                "message": str(result_payload["overall_conclusion"]),
                "conclusion_markdown": result_payload["conclusion_markdown"],
                "report_markdown": result_payload["report_markdown"],
                "risk_count_summary": result_payload["risk_count_summary"],
                "top_risks": result_payload["top_risks"],
                "downloadable_files": result_payload["downloadable_files"],
                "status_api_url": result_payload["status_api_url"],
                "result_api_url": result_payload["result_api_url"],
                "page_url": result_payload["page_url"],
                "generated_at": result_payload["generated_at"],
            }

        if task.internal_status == "failed":
            return {
                "page_state": "failed",
                "status_label": "任务失败",
                "summary_title": "审查未完成",
                "overall_conclusion": task.status_message,
                "title": "审查未完成",
                "file_name": task.file_name,
                "message": task.status_message,
                "error_code": task.error_code,
                "status_api_url": f"/api/v1/review-tasks/{task_id}",
                "page_url": f"/review-tasks/{task_id}/page",
            }

        return {
            "page_state": "reviewing",
            "status_label": "审核中",
            "summary_title": "审查进行中",
            "overall_conclusion": task.status_message,
            "title": "审查进行中",
            "file_name": task.file_name,
            "message": task.status_message,
            "status_api_url": f"/api/v1/review-tasks/{task_id}",
            "result_api_url": f"/api/v1/review-tasks/{task_id}/result",
            "page_url": f"/review-tasks/{task_id}/page",
        }

    @staticmethod
    def _validate_upload(upload_file: UploadFile) -> str:
        if not upload_file.filename:
            raise UploadValidationError(400, "MISSING_FILE_NAME", "缺少文件名。")
        if not upload_file.content:
            raise UploadValidationError(400, "EMPTY_FILE", "上传文件不能为空。")
        extension = Path(upload_file.filename).suffix.lower()
        file_type = SUPPORTED_TYPES.get(extension)
        if file_type is None:
            raise UploadValidationError(415, "UNSUPPORTED_FILE_TYPE", "仅支持 PDF 或 Word 文件。")
        return file_type
