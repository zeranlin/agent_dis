from __future__ import annotations

import re
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
            seen_clause_texts: set[str] = set()

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
                chapter_title = str(chapter_payload["chapter_title"])
                clause_type = "条款片段" if block.block_type == "clause" else "段落片段"
                module_type = _classify_business_module(
                    chapter_title=chapter_title,
                    block_title=str(block.title),
                    text=str(block.text),
                )
                clause_slices = _build_reviewable_clause_slices(block=block)
                review_unit_id = f"unit_{block.block_id}"
                parent_unit_id = review_unit_id if len(clause_slices) > 1 else None
                for slice_index, clause_slice in enumerate(clause_slices, start=1):
                    normalized_text = _normalize_clause_text(clause_slice["text"])
                    if not normalized_text or normalized_text in seen_clause_texts:
                        continue
                    seen_clause_texts.add(normalized_text)
                    clause_count += 1
                    unit_type, unit_label, unit_name = _classify_review_unit(
                        module_type=module_type,
                        clause_type=clause_type,
                        chapter_title=chapter_title,
                        block_title=str(block.title),
                        source_anchor=str(clause_slice["anchor"]),
                        text=clause_slice["text"],
                    )
                    self.repository.save_clause(
                        build_clause_record(
                            clause_id=f"clause_{uuid4().hex[:12]}",
                            document_id=document.document_id,
                            chapter_id=parent_chapter_id,
                            chapter_title=chapter_title,
                            review_unit_id=review_unit_id,
                            module_type=module_type,
                            unit_type=unit_type,
                            unit_label=unit_label,
                            unit_name=unit_name,
                            clause_order=(block.order_index * 100) + slice_index,
                            clause_text=clause_slice["text"],
                            location_label=f"{chapter_title} / {clause_slice['anchor']}",
                            parent_unit_id=parent_unit_id,
                            clause_type=clause_type,
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


SUBITEM_PATTERN = re.compile(r"^(?:\(?\d+\)?[、.)]|[（(]\d+[)）]|[（(][一二三四五六七八九十]+[)）]|[a-zA-Z][、.)])")
SHORT_ANCHOR_MAX_LEN = 48
LONG_CLAUSE_THRESHOLD = 280
LONG_SEGMENT_THRESHOLD = 90
PIPE_SPLIT_PATTERN = re.compile(r"\s*\|\s*")
BUSINESS_MODULE_KEYWORDS = {
    "项目基础信息": ("项目名称", "项目编号", "采购人", "代理机构", "预算金额", "采购方式"),
    "资格条件": ("资格", "资质", "证书", "业绩", "注册", "办公", "信用"),
    "采购需求": ("采购需求", "技术", "参数", "规格", "性能", "配置", "功能", "服务要求", "交付"),
    "评分办法": ("评分", "评审", "打分", "分值", "综合评价", "价格分", "商务分", "技术分"),
    "合同条款": ("合同", "付款", "违约", "验收", "履约", "质保", "责任"),
    "程序条款": ("投标", "开标", "评标", "定标", "废标", "澄清", "质疑", "投诉", "公告", "提交"),
    "政策条款": ("中小企业", "绿色", "环保", "节能", "进口产品", "政策"),
}
TABLE_ROW_HINTS = ("|", "｜")
DEVIATION_KEYWORDS = ("偏离", "偏差", "响应情况", "响应偏离")
QUALIFICATION_PERFORMANCE_KEYWORDS = ("业绩", "案例", "经验")
QUALIFICATION_CERT_KEYWORDS = ("资质", "证书", "认证", "许可", "执业", "资格证")
QUALIFICATION_CREDIT_KEYWORDS = ("信用", "失信", "信誉")
PROCUREMENT_DELIVERY_KEYWORDS = ("交付", "供货期", "工期", "到货", "实施周期")
PROCUREMENT_SERVICE_KEYWORDS = ("服务", "驻场", "培训", "维护", "售后")
PROCUREMENT_FUNCTION_KEYWORDS = ("功能", "配置", "接口", "模块")
SCORE_PRICE_KEYWORDS = ("价格分", "报价分", "价格评审")
SCORE_BUSINESS_KEYWORDS = ("商务分", "商务评审", "企业实力", "业绩分")
SCORE_TECH_KEYWORDS = ("技术分", "技术评审", "技术响应")
CONTRACT_PAYMENT_KEYWORDS = ("付款", "支付", "结算")
CONTRACT_ACCEPTANCE_KEYWORDS = ("验收", "初验", "终验")
CONTRACT_BREACH_KEYWORDS = ("违约", "罚则", "赔偿", "追偿")
CONTRACT_WARRANTY_KEYWORDS = ("质保", "保修", "售后")
CONTRACT_EXPENSE_KEYWORDS = ("费用", "承担", "风险", "保险")
GENERIC_TABLE_HEADER_KEYWORDS = (
    "序号",
    "条款号",
    "评分项",
    "分值",
    "内容",
    "要求",
    "指标",
    "响应情况",
    "参数名称",
    "指标要求",
)


def _normalize_clause_text(text: str) -> str:
    return re.sub(r"\s+", "", str(text))


def _build_reviewable_clause_slices(*, block: object) -> list[dict[str, str]]:
    text = str(block.text).strip()
    anchor = _build_location_anchor(block.source_anchor or block.title or f"片段{block.order_index}")
    if not text:
        return []

    if block.block_type != "clause":
        return [{"anchor": anchor, "text": text}]

    segments = _split_long_clause_text(text)
    if len(segments) <= 1:
        return [{"anchor": anchor, "text": text}]

    slices: list[dict[str, str]] = []
    for index, segment in enumerate(segments, start=1):
        segment_anchor = anchor if index == 1 else f"{anchor}（片段{index}）"
        slices.append({"anchor": segment_anchor, "text": segment})
    return slices


def _build_location_anchor(raw_anchor: str) -> str:
    anchor = str(raw_anchor).replace("\n", " ").strip()
    if not anchor:
        return "片段"

    if "|" in anchor:
        parts = [part.strip() for part in PIPE_SPLIT_PATTERN.split(anchor) if part.strip()]
        meaningful_parts = [part for part in parts if len(part) > 1]
        if meaningful_parts:
            anchor = " / ".join(meaningful_parts[:2])
        elif parts:
            anchor = parts[0]

    anchor = re.sub(r"\s+", " ", anchor)
    if len(anchor) <= SHORT_ANCHOR_MAX_LEN:
        return anchor
    return f"{anchor[:SHORT_ANCHOR_MAX_LEN].rstrip()}..."


def _split_long_clause_text(text: str) -> list[str]:
    normalized_text = str(text).strip()
    pipe_segments = [part.strip() for part in PIPE_SPLIT_PATTERN.split(normalized_text) if part.strip()]
    should_force_split = len(pipe_segments) >= 4 and len(normalized_text) >= 140
    if len(normalized_text) <= LONG_CLAUSE_THRESHOLD and not should_force_split:
        return [normalized_text]

    lines = [line.strip() for line in normalized_text.splitlines() if line.strip()]
    heading = lines[0] if len(lines) > 1 else ""
    remainder = lines[1:] if len(lines) > 1 else [normalized_text]
    if not remainder:
        remainder = [normalized_text]

    units: list[str] = []
    for line in remainder:
        pipe_parts = [part.strip() for part in PIPE_SPLIT_PATTERN.split(line) if part.strip()]
        if len(pipe_parts) >= 3:
            units.extend(pipe_parts)
            continue
        units.append(line)

    grouped_units: list[str] = []
    current_parts: list[str] = []
    for unit in units:
        candidate = " ".join(current_parts + [unit]).strip()
        should_break = (
            current_parts
            and (
                SUBITEM_PATTERN.match(unit)
                or len(candidate) > LONG_CLAUSE_THRESHOLD
                or (len(current_parts[-1]) >= LONG_SEGMENT_THRESHOLD and len(unit) >= LONG_SEGMENT_THRESHOLD)
            )
        )
        if should_break:
            grouped_units.append(" ".join(current_parts).strip())
            current_parts = [unit]
        else:
            current_parts.append(unit)
    if current_parts:
        grouped_units.append(" ".join(current_parts).strip())

    if len(grouped_units) <= 1:
        return [normalized_text]

    slices: list[str] = []
    for unit in grouped_units:
        if len(unit) < 20:
            if slices:
                slices[-1] = f"{slices[-1]} {unit}".strip()
            else:
                slices.append(f"{heading} {unit}".strip())
            continue
        if heading:
            slices.append(f"{heading}\n{unit}".strip())
        else:
            slices.append(unit)

    return slices or [normalized_text]


def _classify_business_module(*, chapter_title: str, block_title: str, text: str) -> str:
    best_module_type = "其他"
    best_score = 0
    for module_type, keywords in BUSINESS_MODULE_KEYWORDS.items():
        score = 0
        for keyword in keywords:
            if keyword in chapter_title:
                score += 3
            if keyword in block_title:
                score += 2
            if keyword in text:
                score += 1
        if score > best_score:
            best_module_type = module_type
            best_score = score
    return best_module_type


def _classify_review_unit(
    *,
    module_type: str,
    clause_type: str,
    chapter_title: str,
    block_title: str,
    source_anchor: str,
    text: str,
) -> tuple[str, str, str]:
    normalized_text = str(text)
    combined_text = f"{chapter_title}\n{block_title}\n{normalized_text}"
    is_table_row = any(marker in normalized_text for marker in TABLE_ROW_HINTS)
    unit_name = _extract_unit_name(
        clause_type=clause_type,
        block_title=block_title,
        source_anchor=source_anchor,
        text=normalized_text,
    )

    if any(keyword in combined_text for keyword in DEVIATION_KEYWORDS):
        return "偏离项", "单个偏离项", unit_name

    if module_type == "资格条件":
        if any(keyword in combined_text for keyword in QUALIFICATION_PERFORMANCE_KEYWORDS):
            return "条款", "单条业绩要求", unit_name
        if any(keyword in combined_text for keyword in QUALIFICATION_CERT_KEYWORDS):
            return "条款", "单条资质要求", unit_name
        if any(keyword in combined_text for keyword in QUALIFICATION_CREDIT_KEYWORDS):
            return "条款", "单条信用要求", unit_name
        return "条款", "单条资格要求", unit_name

    if module_type == "采购需求":
        if any(keyword in combined_text for keyword in PROCUREMENT_DELIVERY_KEYWORDS):
            return "参数项", "单条交付要求", unit_name
        if any(keyword in combined_text for keyword in PROCUREMENT_SERVICE_KEYWORDS):
            return "参数项", "单条服务要求", unit_name
        if any(keyword in combined_text for keyword in PROCUREMENT_FUNCTION_KEYWORDS):
            return "参数项", "单条功能要求", unit_name
        if is_table_row:
            return "参数项", "单个参数项", unit_name
        return "参数项", "单条技术参数", unit_name

    if module_type == "评分办法":
        if any(keyword in combined_text for keyword in SCORE_PRICE_KEYWORDS):
            return "评分项", "价格分规则", unit_name
        if any(keyword in combined_text for keyword in SCORE_BUSINESS_KEYWORDS):
            return "评分项", "商务分规则", unit_name
        if any(keyword in combined_text for keyword in SCORE_TECH_KEYWORDS):
            return "评分项", "技术分规则", unit_name
        return "评分项", "单个评分项", unit_name

    if module_type == "合同条款":
        if any(keyword in combined_text for keyword in CONTRACT_PAYMENT_KEYWORDS):
            return "合同项", "付款条款", unit_name
        if any(keyword in combined_text for keyword in CONTRACT_ACCEPTANCE_KEYWORDS):
            return "合同项", "验收条款", unit_name
        if any(keyword in combined_text for keyword in CONTRACT_BREACH_KEYWORDS):
            return "合同项", "违约责任条款", unit_name
        if any(keyword in combined_text for keyword in CONTRACT_WARRANTY_KEYWORDS):
            return "合同项", "质保条款", unit_name
        if any(keyword in combined_text for keyword in CONTRACT_EXPENSE_KEYWORDS):
            return "合同项", "费用承担条款", unit_name
        return "合同项", "单条合同条款", unit_name

    if is_table_row:
        return "表格行", "普通表格行", unit_name
    return "条款", "普通条款", unit_name


def _extract_unit_name(*, clause_type: str, block_title: str, source_anchor: str, text: str) -> str:
    if "表格" in clause_type or any(marker in text for marker in TABLE_ROW_HINTS):
        for line in [item.strip() for item in str(text).splitlines() if item.strip()]:
            if not any(marker in line for marker in TABLE_ROW_HINTS):
                continue
            cells = [part.strip() for part in PIPE_SPLIT_PATTERN.split(line) if part.strip()]
            meaningful_cells = [
                cell
                for cell in cells[:3]
                if not cell.isdigit() and cell not in GENERIC_TABLE_HEADER_KEYWORDS
            ]
            if meaningful_cells:
                return _truncate_unit_name(meaningful_cells[0])
            if cells and not all(cell in GENERIC_TABLE_HEADER_KEYWORDS for cell in cells):
                return _truncate_unit_name(cells[0])

    for candidate in (block_title, source_anchor):
        cleaned = str(candidate).strip()
        if cleaned:
            return _truncate_unit_name(cleaned)

    first_line = str(text).splitlines()[0].strip() if str(text).splitlines() else ""
    return _truncate_unit_name(first_line or "未命名单元")


def _truncate_unit_name(value: str) -> str:
    cleaned = re.sub(r"\s+", " ", str(value)).strip()
    if len(cleaned) <= 36:
        return cleaned
    return f"{cleaned[:36].rstrip()}..."
