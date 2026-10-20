# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import re
import tempfile
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET


DOCUMENT_TITLE_ROLE = "document_title"
SECTION_TITLE_ROLE = "title"
AUTO_TITLE_ROLES = {DOCUMENT_TITLE_ROLE, SECTION_TITLE_ROLE}
DOCUMENT_TITLE_TOKEN = "__JB_AUTO_DOC_TITLE_SLOT_7F3A91__"
SECTION_NUMBER_TOKEN = "__JB_AUTO_SECTION_NUMBER_SLOT_6C4D82__"
SECTION_TITLE_TOKEN = "__JB_AUTO_SECTION_TITLE_SLOT_5B8E73__"
_TEXT_TAG_SUFFIX = "}t"
_NUMBER_ONLY_RE = re.compile(
    r"^(?:\d+[.)]?|[가-하][.)]?|[IVXLCDMivxlcdm]+[.)]?|"
    r"[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩⅪⅫⅰⅱⅲⅳⅴⅵⅶⅷⅸⅹ]+[.)]?|[①-⑳]|[○□•*\-])$"
)
_COMBINED_NUMBER_RE = re.compile(
    r"^\s*((?:\d+|[가-하]|[IVXLCDMivxlcdm]+|"
    r"[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩⅪⅫⅰⅱⅲⅳⅴⅵⅶⅷⅸⅹ]+)[.)]?|[①-⑳]|[○□•*\-])\s+(.+?)\s*$"
)


class AutoTitleTemplateError(ValueError):
    pass


def normalize_role(role: str) -> str:
    value = str(role or "").strip()
    if value not in AUTO_TITLE_ROLES:
        raise AutoTitleTemplateError("지원하지 않는 자동 서식 제목 종류입니다.")
    return value


def _segments(raw_text: str) -> list[str]:
    values = []
    for part in re.split(r"[\t\r\n]+", str(raw_text or "")):
        clean = " ".join(part.strip().split())
        if clean and clean not in values:
            values.append(clean)
    return values


def analyze_example_text(role: str, raw_text: str) -> dict[str, object]:
    role = normalize_role(role)
    segments = _segments(raw_text)
    if not segments:
        raise AutoTitleTemplateError(
            "블록 안에서 예시 글자를 찾지 못했습니다. 예시 번호와 제목을 입력한 뒤 다시 블록 지정하세요."
        )

    if role == DOCUMENT_TITLE_ROLE:
        title = max(segments, key=lambda value: (len(value), value))
        return {
            "role": role,
            "number_sample": "",
            "title_sample": title,
            "segments": segments,
            "combined": False,
        }

    number = next((value for value in segments if _NUMBER_ONLY_RE.fullmatch(value)), "")
    title_candidates = [value for value in segments if value != number]
    if number and title_candidates:
        title = max(title_candidates, key=lambda value: (len(value), value))
        return {
            "role": role,
            "number_sample": number,
            "title_sample": title,
            "segments": segments,
            "combined": False,
        }

    for value in segments:
        match = _COMBINED_NUMBER_RE.match(value)
        if match:
            return {
                "role": role,
                "number_sample": match.group(1).strip(),
                "title_sample": match.group(2).strip(),
                "segments": segments,
                "combined": True,
            }

    raise AutoTitleTemplateError(
        "1단계 제목의 예시 번호와 제목을 구분하지 못했습니다. "
        "예: '1'과 '추진 배경' 또는 '1. 추진 배경'을 넣은 뒤 다시 블록 지정하세요."
    )


def _text_nodes(root: ET.Element) -> list[ET.Element]:
    return [
        element
        for element in root.iter()
        if element.tag == "t" or str(element.tag).endswith(_TEXT_TAG_SUFFIX)
    ]


def _replace_across_text_nodes(
    root: ET.Element,
    needle: str,
    replacement: str,
) -> bool:
    target = str(needle or "")
    if not target:
        return False
    nodes = _text_nodes(root)
    pieces = [str(node.text or "") for node in nodes]
    joined = "".join(pieces)
    start = joined.find(target)
    if start < 0:
        return False
    end = start + len(target)
    cursor = 0
    inserted = False
    for node, value in zip(nodes, pieces):
        node_start = cursor
        node_end = cursor + len(value)
        cursor = node_end
        overlap_start = max(start, node_start)
        overlap_end = min(end, node_end)
        if overlap_start >= overlap_end:
            continue
        local_start = overlap_start - node_start
        local_end = overlap_end - node_start
        prefix = value[:local_start]
        suffix = value[local_end:]
        if not inserted:
            node.text = prefix + replacement + suffix
            inserted = True
        else:
            node.text = prefix + suffix
    return inserted


def _register_namespaces(xml_data: bytes) -> None:
    head = xml_data[:8192].decode("utf-8", errors="ignore")
    for prefix, uri in re.findall(r'xmlns:([A-Za-z0-9_]+)="([^"]+)"', head):
        try:
            ET.register_namespace(prefix, uri)
        except Exception:
            pass


def prepare_hwpx_template(
    source_path: str | os.PathLike[str],
    destination_path: str | os.PathLike[str],
    *,
    role: str,
    title_sample: str,
    number_sample: str = "",
) -> dict[str, str]:
    role = normalize_role(role)
    source = Path(source_path)
    destination = Path(destination_path)
    if not source.is_file() or not zipfile.is_zipfile(source):
        raise AutoTitleTemplateError("제목 양식을 HWPX 형식으로 저장하지 못했습니다.")

    title_sample = str(title_sample or "").strip()
    number_sample = str(number_sample or "").strip()
    if not title_sample:
        raise AutoTitleTemplateError("제목으로 사용할 예시 글자를 확인하세요.")
    if role == SECTION_TITLE_ROLE and not number_sample:
        raise AutoTitleTemplateError("번호로 사용할 예시 글자를 확인하세요.")

    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        prefix=f".{destination.stem}_",
        suffix=".hwpx",
        dir=str(destination.parent),
    )
    os.close(fd)
    temp_path = Path(temp_name)
    title_replaced = False
    number_replaced = role == DOCUMENT_TITLE_ROLE
    try:
        with zipfile.ZipFile(source, "r") as input_zip, zipfile.ZipFile(temp_path, "w") as output_zip:
            for info in input_zip.infolist():
                data = input_zip.read(info.filename)
                if info.filename.startswith("Contents/section") and info.filename.endswith(".xml"):
                    _register_namespaces(data)
                    root = ET.fromstring(data)
                    if not title_replaced:
                        title_replaced = _replace_across_text_nodes(
                            root, title_sample, DOCUMENT_TITLE_TOKEN if role == DOCUMENT_TITLE_ROLE else SECTION_TITLE_TOKEN
                        )
                    if role == SECTION_TITLE_ROLE and not number_replaced:
                        number_replaced = _replace_across_text_nodes(
                            root, number_sample, SECTION_NUMBER_TOKEN
                        )
                    data = ET.tostring(root, encoding="utf-8", xml_declaration=True)
                output_zip.writestr(info, data)
        if not title_replaced:
            raise AutoTitleTemplateError(
                "저장된 제목 양식에서 번호와 제목 위치를 찾지 못했습니다. 인식 결과를 확인하세요."
            )
        if not number_replaced:
            raise AutoTitleTemplateError(
                "저장된 블록에서 번호 예시 글자의 위치를 찾지 못했습니다. 인식 결과를 확인하세요."
            )
        os.replace(temp_path, destination)
    finally:
        temp_path.unlink(missing_ok=True)

    return {
        "title_token": DOCUMENT_TITLE_TOKEN if role == DOCUMENT_TITLE_ROLE else SECTION_TITLE_TOKEN,
        "number_token": SECTION_NUMBER_TOKEN if role == SECTION_TITLE_ROLE else "",
    }