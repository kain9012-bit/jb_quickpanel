# -*- coding: utf-8 -*-
from __future__ import annotations

import html
import re
import ssl
import urllib.request


UPDATE_POST_URL = (
    "https://www.jbe.go.kr/board/view.jbe?boardId=BBS_0000649"
    "&menuCd=DOM_000000106011002000&paging=ok&startPage=1"
    "&searchOperation=AND&dataSid=1151988"
)

_SEGMENT_RE = re.compile(r"\[업데이트정보\]([^<\r\n]+)")


def _parse_fields(segment: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for part in segment.split("|"):
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        fields[key.strip()] = value.strip()
    return fields


def _version_tuple(text: str) -> tuple[int, ...]:
    numbers = re.findall(r"\d+", text or "")
    return tuple(int(number) for number in numbers) if numbers else (0,)


def check_update(app_id: str, current_version: str, timeout: float = 6.0) -> dict:
    try:
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        request = urllib.request.Request(
            UPDATE_POST_URL,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        with urllib.request.urlopen(request, timeout=timeout, context=context) as response:
            raw = response.read().decode("utf-8", "replace")
    except Exception as exc:
        return {"ok": False, "reason": "network", "error": str(exc)}

    target = str(app_id).strip()
    for segment in _SEGMENT_RE.findall(html.unescape(raw)):
        fields = _parse_fields(segment)
        if fields.get("id", "").strip() != target:
            continue
        version = fields.get("버전") or fields.get("version")
        download = fields.get("다운로드") or fields.get("download")
        if version and download:
            return {
                "ok": True,
                "version": version.strip(),
                "download": download.strip(),
                "current": current_version,
                "is_newer": _version_tuple(version) > _version_tuple(current_version),
            }

    return {"ok": False, "reason": "not_registered"}