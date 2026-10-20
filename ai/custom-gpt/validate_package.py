from __future__ import annotations

import re
import sys
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parent
REPOSITORY_ROOT = PACKAGE_ROOT.parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from src.jb_quickpanel.features.auto_format import (  # noqa: E402
    detect_report_tag,
    transform_report_text,
)


EXAMPLES_FILE = PACKAGE_ROOT / "knowledge" / "04_작성예시.md"
REQUIRED_FILES = (
    PACKAGE_ROOT / "instructions.md",
    PACKAGE_ROOT / "knowledge" / "01_서식도우미_출력규격.md",
    PACKAGE_ROOT / "knowledge" / "02_공무원_보고서_작성원칙.md",
    PACKAGE_ROOT / "knowledge" / "03_기본문서유형.md",
    EXAMPLES_FILE,
    PACKAGE_ROOT / "evals" / "품질평가_사례.md",
)


def extract_examples(text: str) -> list[tuple[str, str]]:
    matches = list(re.finditer(r"^## (.+ 예시)\s*$", text, flags=re.MULTILINE))
    examples = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        block = text[match.end() : end].strip()
        start = block.find("(문서제목)")
        if start < 0:
            raise AssertionError(f"{match.group(1)}에 문서제목이 없습니다.")
        examples.append((match.group(1), block[start:].strip()))
    return examples


def validate_example(name: str, text: str) -> None:
    title_count = 0
    in_table = False
    expected_columns = None
    table_count = 0

    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        tag, _content = detect_report_tag(line)
        if in_table:
            if tag == "표끝":
                in_table = False
                expected_columns = None
                continue
            if tag is not None:
                raise AssertionError(
                    f"{name} {line_number}행: 표 안에 태그가 들어갔습니다."
                )
            columns = len(line.split("|"))
            if expected_columns is None:
                expected_columns = columns
            elif columns != expected_columns:
                raise AssertionError(
                    f"{name} {line_number}행: 표 열 개수가 {expected_columns}개가 아닙니다."
                )
            continue

        if tag is None:
            raise AssertionError(f"{name} {line_number}행: 태그 없는 문단입니다: {line}")
        if tag == "문서제목":
            title_count += 1
        elif tag == "표시작":
            in_table = True
            table_count += 1
        elif tag == "표끝":
            raise AssertionError(f"{name} {line_number}행: 표끝만 존재합니다.")

    if in_table:
        raise AssertionError(f"{name}: 표끝이 없습니다.")
    if title_count != 1:
        raise AssertionError(f"{name}: 문서제목이 {title_count}개입니다.")

    items, changed_count = transform_report_text(text)
    if changed_count <= 0:
        raise AssertionError(f"{name}: 서식도우미가 태그를 인식하지 못했습니다.")
    parsed_tables = sum(1 for item in items if item.get("tag") == "표")
    if parsed_tables != table_count:
        raise AssertionError(
            f"{name}: 표 {table_count}개 중 {parsed_tables}개만 변환됐습니다."
        )


def main() -> int:
    missing = [str(path) for path in REQUIRED_FILES if not path.is_file()]
    if missing:
        raise AssertionError("필수 파일이 없습니다:\n" + "\n".join(missing))

    examples = extract_examples(EXAMPLES_FILE.read_text(encoding="utf-8"))
    if len(examples) != 3:
        raise AssertionError(f"작성 예시는 3개여야 합니다. 현재 {len(examples)}개입니다.")
    for name, text in examples:
        validate_example(name, text)
        print(f"OK: {name}")
    print(f"Custom GPT 패키지 검증 완료: 예시 {len(examples)}개")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
