# -*- coding: utf-8 -*-
from __future__ import annotations

from copy import deepcopy
import re
from typing import Any


AUTO_FORMAT_ROLE_DEFAULTS = {
    "document_title": {"font": "HY헤드라인M", "size": 23, "bold": True},
    "title": {
        "font": "HY헤드라인M",
        "size": 16,
        "bold": False,
        "marker": "number_dot",
        "custom_marker": "",
    },
    "subtitle": {
        "font": "휴먼명조",
        "size": 14,
        "bold": True,
        "marker": "hangul_dot",
        "custom_marker": "",
    },
    "subsubtitle": {
        "font": "휴먼명조",
        "size": 13,
        "bold": True,
        "marker": "number_paren",
        "custom_marker": "",
    },
    "body": {
        "font": "휴먼명조",
        "size": 13,
        "bold": False,
        "marker": "dash",
        "custom_marker": "",
    },
    "table": {"font": "굴림체", "size": 12, "bold": False},
    "reference": {
        "font": "맑은 고딕",
        "size": 11,
        "bold": False,
        "marker": "reference",
        "custom_marker": "",
    },
}

DEFAULT_AUTO_FORMAT_SETTINGS = {
    "document_title_template": "auto-title-builtin:document_title",
    "title_template": "auto-title-builtin:title",
    "roles": deepcopy(AUTO_FORMAT_ROLE_DEFAULTS),
}

DEFAULT_AUTO_FORMAT_PROFILE_ID = "default"
MAX_AUTO_FORMAT_PROFILES = 10

_SEQUENCE_MARKER_ORDER = (
    "number_dot",
    "number_paren",
    "hangul_dot",
    "hangul_paren",
    "roman_upper_dot",
    "roman_lower_dot",
    "number_circle",
)
_SEQUENCE_MARKERS = set(_SEQUENCE_MARKER_ORDER)
_HEADING_MARKERS = _SEQUENCE_MARKERS | {"circle", "square", "dash", "custom", "none"}
ROLE_MARKERS = {
    "document_title": {"none"},
    "title": set(_HEADING_MARKERS),
    "subtitle": set(_HEADING_MARKERS),
    "subsubtitle": set(_HEADING_MARKERS),
    "body": {"dash", "asterisk", "circle", "square", "bullet", "custom", "none"},
    "table": {"none"},
    "reference": {"reference", "asterisk", "custom", "none"},
}


def _normalized_role(role: str, value: Any) -> dict[str, Any]:
    default = AUTO_FORMAT_ROLE_DEFAULTS[role]
    source = value if isinstance(value, dict) else {}
    font = " ".join(str(source.get("font") or default["font"]).strip().split())
    if not font or len(font) > 60:
        font = str(default["font"])
    try:
        size = int(source.get("size", default["size"]))
    except (TypeError, ValueError):
        size = int(default["size"])
    size = min(72, max(5, size))
    result: dict[str, Any] = {
        "font": font,
        "size": size,
        "bold": bool(source.get("bold", default["bold"])),
    }
    if "marker" in default:
        marker = str(source.get("marker") or default["marker"])
        if marker not in ROLE_MARKERS[role]:
            marker = str(default["marker"])
        result["marker"] = marker
        result["custom_marker"] = str(source.get("custom_marker") or "").strip()[:8]
    return result


def _deduplicate_heading_markers(roles: dict[str, dict[str, Any]]) -> None:
    used: set[str] = set()
    fallback_order = ("number_dot", "hangul_dot", "number_paren")
    for index, role in enumerate(("title", "subtitle", "subsubtitle")):
        marker = str(roles[role].get("marker") or "none")
        if marker in _SEQUENCE_MARKERS and marker in used:
            fallback = fallback_order[index]
            if fallback in used:
                fallback = next(item for item in _SEQUENCE_MARKER_ORDER if item not in used)
            roles[role]["marker"] = fallback
            marker = fallback
        if marker in _SEQUENCE_MARKERS:
            used.add(marker)


def normalize_auto_format_settings(value: Any) -> dict[str, Any]:
    source = value if isinstance(value, dict) else {}
    role_values = source.get("roles") if isinstance(source.get("roles"), dict) else {}

    def template_key(name: str, fallback: str, role: str) -> str:
        key = str(source.get(name) or fallback).strip()
        legacy = {
            "document_title": "builtin:b01",
            "title": "builtin:b04",
        }
        if key == legacy[role]:
            return fallback
        if (
            key in {f"auto-title-builtin:{role}", f"auto-title-none:{role}"}
            or key.startswith("auto-title-user:")
        ):
            return key[:160]
        return fallback

    roles = {
        role: _normalized_role(role, role_values.get(role))
        for role in AUTO_FORMAT_ROLE_DEFAULTS
    }
    _deduplicate_heading_markers(roles)
    return {
        "document_title_template": template_key(
            "document_title_template",
            str(DEFAULT_AUTO_FORMAT_SETTINGS["document_title_template"]),
            "document_title",
        ),
        "title_template": template_key(
            "title_template",
            str(DEFAULT_AUTO_FORMAT_SETTINGS["title_template"]),
            "title",
        ),
        "roles": roles,
    }


def default_auto_format_profiles() -> list[dict[str, Any]]:
    return [
        {
            "id": DEFAULT_AUTO_FORMAT_PROFILE_ID,
            "name": "기본 설정",
            "settings": deepcopy(DEFAULT_AUTO_FORMAT_SETTINGS),
        }
    ]


def normalize_auto_format_profile_state(
    profiles_value: Any,
    active_profile_id: Any,
    legacy_settings: Any,
) -> dict[str, Any]:
    source = profiles_value if isinstance(profiles_value, list) else []
    profiles: list[dict[str, Any]] = []
    used_ids: set[str] = set()
    used_names: set[str] = set()

    for index, raw in enumerate(source, start=1):
        if not isinstance(raw, dict):
            continue
        raw_id = str(raw.get("id") or "").strip()[:64]
        profile_id = raw_id if re.fullmatch(r"[A-Za-z0-9:_-]+", raw_id) else ""
        if not profile_id or profile_id in used_ids:
            profile_id = f"profile-{index}"
            suffix = 2
            while profile_id in used_ids:
                profile_id = f"profile-{index}-{suffix}"
                suffix += 1

        base_name = " ".join(str(raw.get("name") or "").strip().split())[:40]
        if not base_name:
            base_name = f"자동 서식 설정 {index}"
        name = base_name
        suffix = 2
        while name.casefold() in used_names:
            tail = f" ({suffix})"
            name = (base_name[: max(1, 40 - len(tail))] + tail).strip()
            suffix += 1

        profiles.append(
            {
                "id": profile_id,
                "name": name,
                "settings": normalize_auto_format_settings(raw.get("settings")),
            }
        )
        used_ids.add(profile_id)
        used_names.add(name.casefold())

    if not profiles:
        profiles = [
            {
                "id": DEFAULT_AUTO_FORMAT_PROFILE_ID,
                "name": "기본 설정",
                "settings": normalize_auto_format_settings(legacy_settings),
            }
        ]

    requested_id = str(active_profile_id or "").strip()
    active = next(
        (profile for profile in profiles if profile["id"] == requested_id),
        profiles[0],
    )
    return {
        "auto_format_profiles": profiles,
        "active_auto_format_profile": active["id"],
        "auto_format": deepcopy(active["settings"]),
    }
