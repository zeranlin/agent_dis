from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree


CHAPTER_PATTERN = re.compile(r"^(第[一二三四五六七八九十百]+章.*|[一二三四五六七八九十]+、.*|\d+[、.]\D.*)$")
CLAUSE_PATTERN = re.compile(r"^(\d+(?:\.\d+){0,3}[、.]?.*|第[一二三四五六七八九十]+条.*)$")
PAGE_NUMBER_PATTERN = re.compile(r"^(?:第?\d+页|\d+/\d+|\d+)$")
W_NAMESPACE = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}


class ParseFailure(Exception):
    def __init__(self, error_code: str, user_message: str, detail_message: str):
        super().__init__(detail_message)
        self.error_code = error_code
        self.user_message = user_message
        self.detail_message = detail_message


@dataclass
class ParsedBlock:
    block_id: str
    block_type: str
    title: str
    text: str
    source_page_start: int
    source_page_end: int
    order_index: int
    parent_block_id: str | None
    source_anchor: str


@dataclass
class ParsedDocument:
    raw_text: str
    page_count: int
    blocks: list[ParsedBlock]


def parse_document(path: Path) -> ParsedDocument:
    content = path.read_bytes()
    if not content:
        raise ParseFailure("DOCUMENT_EMPTY", "文件无法读取", "文件为空，无法进入解析。")

    suffix = path.suffix.lower()
    if suffix == ".docx":
        raw_text = _extract_docx_text(content)
    elif suffix == ".pdf":
        raw_text = _extract_pdf_text(content)
    elif suffix == ".doc":
        raw_text = _extract_doc_text(content)
    else:
        raise ParseFailure("DOCUMENT_PARSE_UNSUPPORTED", "文件格式不支持", f"暂不支持解析 {suffix} 文件。")

    cleaned_text = clean_review_text(raw_text)
    if not is_reviewable_text(cleaned_text):
        raise ParseFailure(
            "DOCUMENT_NO_REVIEWABLE_TEXT",
            "文件无可审查正文",
            "文件未能提取出连续、可审查的正文文本。",
        )

    page_count = estimate_page_count(content, suffix, cleaned_text)
    blocks = segment_document(cleaned_text, page_count)
    if not any(block.block_type != "section" for block in blocks):
        raise ParseFailure(
            "DOCUMENT_NO_REVIEWABLE_TEXT",
            "文件无可审查正文",
            "文件仅识别到章节标题，未形成可审查片段。",
        )
    return ParsedDocument(raw_text=cleaned_text, page_count=page_count, blocks=blocks)


def clean_review_text(raw_text: str) -> str:
    normalized = raw_text.replace("\r\n", "\n").replace("\r", "\n").replace("\u3000", " ")
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in normalized.split("\n")]
    non_empty_lines = [line for line in lines if line]
    if not non_empty_lines:
        return ""

    repeated_short_lines = {
        line
        for line in non_empty_lines
        if len(line) <= 30 and non_empty_lines.count(line) >= 3
    }

    cleaned_lines: list[str] = []
    for line in non_empty_lines:
        if PAGE_NUMBER_PATTERN.match(line):
            continue
        if line in repeated_short_lines:
            continue
        cleaned_lines.append(line)

    return "\n".join(cleaned_lines).strip()


def is_reviewable_text(text: str) -> bool:
    if len(text) < 40:
        return False

    lines = [line for line in text.splitlines() if line.strip()]
    if len(lines) < 3:
        return False

    meaningful_chars = sum(1 for char in text if _is_meaningful_char(char))
    ratio = meaningful_chars / max(len(text), 1)
    return ratio >= 0.55


def segment_document(text: str, page_count: int) -> list[ParsedBlock]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return []

    blocks: list[ParsedBlock] = []
    current_section_id: str | None = None
    current_clause_anchor: str | None = None
    current_clause_lines: list[str] = []
    paragraph_lines: list[str] = []
    order_index = 1
    block_counter = 1

    def next_block_id() -> str:
        nonlocal block_counter
        block_id = f"block_{block_counter:04d}"
        block_counter += 1
        return block_id

    def emit_paragraph() -> None:
        nonlocal order_index, paragraph_lines
        if not paragraph_lines:
            return
        text_value = "\n".join(paragraph_lines)
        blocks.append(
            ParsedBlock(
                block_id=next_block_id(),
                block_type="paragraph",
                title=paragraph_lines[0][:24],
                text=text_value,
                source_page_start=1,
                source_page_end=page_count,
                order_index=order_index,
                parent_block_id=current_section_id,
                source_anchor=paragraph_lines[0][:40],
            )
        )
        order_index += 1
        paragraph_lines = []

    def emit_clause() -> None:
        nonlocal order_index, current_clause_lines, current_clause_anchor
        if not current_clause_lines:
            return
        text_value = "\n".join(current_clause_lines)
        blocks.append(
            ParsedBlock(
                block_id=next_block_id(),
                block_type="clause",
                title=current_clause_anchor or current_clause_lines[0][:24],
                text=text_value,
                source_page_start=1,
                source_page_end=page_count,
                order_index=order_index,
                parent_block_id=current_section_id,
                source_anchor=current_clause_anchor or current_clause_lines[0][:40],
            )
        )
        order_index += 1
        current_clause_lines = []
        current_clause_anchor = None

    def emit_section(title: str) -> None:
        nonlocal order_index, current_section_id
        current_section_id = next_block_id()
        blocks.append(
            ParsedBlock(
                block_id=current_section_id,
                block_type="section",
                title=title,
                text=title,
                source_page_start=1,
                source_page_end=page_count,
                order_index=order_index,
                parent_block_id=None,
                source_anchor=title,
            )
        )
        order_index += 1

    emit_section("默认章节")

    for line in lines:
        if CLAUSE_PATTERN.match(line):
            emit_paragraph()
            emit_clause()
            current_clause_anchor = line
            current_clause_lines = [line]
            continue

        if CHAPTER_PATTERN.match(line):
            emit_paragraph()
            emit_clause()
            emit_section(line)
            continue

        if current_clause_lines:
            current_clause_lines.append(line)
        else:
            paragraph_lines.append(line)

    emit_paragraph()
    emit_clause()

    meaningful_blocks = [block for block in blocks if block.block_type != "section" or block.title != "默认章节" or len(blocks) == 1]
    return meaningful_blocks


def estimate_page_count(content: bytes, suffix: str, text: str) -> int:
    if "\f" in text:
        return max(1, text.count("\f") + 1)
    if suffix == ".pdf":
        page_markers = len(re.findall(rb"/Type\s*/Page\b", content))
        if page_markers > 0:
            return page_markers
    return 1


def _extract_docx_text(content: bytes) -> str:
    try:
        from io import BytesIO

        with zipfile.ZipFile(BytesIO(content)) as archive:
            document_xml = archive.read("word/document.xml")
    except (KeyError, zipfile.BadZipFile):
        # 保留对历史纯文本测试夹具和简单导出文件的最小兼容兜底。
        return _decode_text_like_content(content)

    try:
        root = ElementTree.fromstring(document_xml)
    except ElementTree.ParseError as exc:
        raise ParseFailure("DOCUMENT_READ_FAILED", "文件无法读取", "DOCX XML 结构解析失败。") from exc

    paragraphs: list[str] = []
    for paragraph in root.findall(".//w:p", W_NAMESPACE):
        texts = [node.text or "" for node in paragraph.findall(".//w:t", W_NAMESPACE)]
        merged = "".join(texts).strip()
        if merged:
            paragraphs.append(merged)
    return "\n".join(paragraphs)


def _extract_pdf_text(content: bytes) -> str:
    if b"/Encrypt" in content:
        raise ParseFailure(
            "DOCUMENT_PASSWORD_PROTECTED",
            "当前文件暂不支持解析，请重新提交更清晰的正文文件",
            "PDF 含有加密标记，当前不支持解析。",
        )

    if not content.lstrip().startswith(b"%PDF"):
        return _decode_text_like_content(content)

    matches = re.findall(rb"\((.*?)\)\s*T[Jj]", content, flags=re.DOTALL)
    if matches:
        return "\n".join(_decode_text_like_content(_unescape_pdf_bytes(item)) for item in matches)

    return _decode_text_like_content(content)


def _extract_doc_text(content: bytes) -> str:
    decoded_candidates = [
        _decode_text_like_content(content),
        content.decode("utf-16le", errors="ignore"),
    ]
    best_text = max(decoded_candidates, key=lambda item: sum(1 for char in item if _is_meaningful_char(char)))
    return best_text


def _decode_text_like_content(content: bytes) -> str:
    candidates: list[str] = []
    for encoding in ("utf-8", "gb18030"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue

    candidates.extend(
        [
            content.decode("utf-8", errors="ignore"),
            content.decode("gb18030", errors="ignore"),
            content.decode("latin1", errors="ignore"),
        ]
    )
    best_text = max(candidates, key=_score_text)
    return best_text


def _unescape_pdf_bytes(value: bytes) -> bytes:
    return (
        value.replace(rb"\n", b"\n")
        .replace(rb"\r", b"")
        .replace(rb"\t", b" ")
        .replace(rb"\(", b"(")
        .replace(rb"\)", b")")
        .replace(rb"\\", b"\\")
    )


def _score_text(text: str) -> tuple[int, int, float]:
    chinese_chars = sum(1 for char in text if "\u4e00" <= char <= "\u9fff")
    alnum_chars = sum(1 for char in text if char.isalnum())
    meaningful_chars = sum(1 for char in text if _is_meaningful_char(char))
    ratio = meaningful_chars / max(len(text), 1)
    return (chinese_chars * 3 + alnum_chars, chinese_chars, ratio)


def _is_meaningful_char(char: str) -> bool:
    if char.isalnum():
        return True
    return "\u4e00" <= char <= "\u9fff"
