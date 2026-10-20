# -*- coding: utf-8 -*-
import tempfile
import unittest
import zipfile
from pathlib import Path

from src.jb_quickpanel.features.auto_title_templates import (
    DOCUMENT_TITLE_TOKEN,
    SECTION_NUMBER_TOKEN,
    SECTION_TITLE_TOKEN,
    analyze_example_text,
    prepare_hwpx_template,
)
from src.jb_quickpanel.services.user_content import UserContentError, UserContentStore


_SECTION_XML = """<?xml version="1.0" encoding="UTF-8"?>
<hs:sec xmlns:hs="urn:section" xmlns:hp="urn:paragraph">
  <hp:p><hp:run><hp:t>{number}</hp:t></hp:run></hp:p>
  <hp:p><hp:run><hp:t>{title_a}</hp:t><hp:t>{title_b}</hp:t></hp:run></hp:p>
</hs:sec>
"""


def _write_hwpx(path: Path, *, number: str, title: str) -> None:
    split_at = max(1, len(title) // 2)
    xml = _SECTION_XML.format(
        number=number,
        title_a=title[:split_at],
        title_b=title[split_at:],
    )
    with zipfile.ZipFile(path, "w") as package:
        package.writestr("mimetype", "application/hwp+zip")
        package.writestr("Contents/section0.xml", xml.encode("utf-8"))


class AutoTitleTemplateTests(unittest.TestCase):
    def test_analyzes_document_and_section_examples(self):
        document = analyze_example_text(
            "document_title", "2026년 찾아가는 교육 운영 계획"
        )
        self.assertEqual(document["title_sample"], "2026년 찾아가는 교육 운영 계획")
        self.assertEqual(document["number_sample"], "")

        separate = analyze_example_text("title", "1\t추진 배경")
        self.assertEqual(separate["number_sample"], "1")
        self.assertEqual(separate["title_sample"], "추진 배경")
        self.assertFalse(separate["combined"])

        combined = analyze_example_text("title", "Ⅰ. 추진 배경")
        self.assertEqual(combined["number_sample"], "Ⅰ.")
        self.assertEqual(combined["title_sample"], "추진 배경")
        self.assertTrue(combined["combined"])

    def test_replaces_examples_across_hwpx_text_nodes(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "source.hwpx"
            destination = Path(folder) / "template.hwpx"
            _write_hwpx(source, number="1", title="추진 배경")

            tokens = prepare_hwpx_template(
                source,
                destination,
                role="title",
                title_sample="추진 배경",
                number_sample="1",
            )

            with zipfile.ZipFile(destination) as package:
                section = package.read("Contents/section0.xml").decode("utf-8")
            self.assertEqual(tokens["number_token"], SECTION_NUMBER_TOKEN)
            self.assertEqual(tokens["title_token"], SECTION_TITLE_TOKEN)
            self.assertIn(SECTION_NUMBER_TOKEN, section)
            self.assertIn(SECTION_TITLE_TOKEN, section)
            self.assertNotIn("추진 배경", section)

    def test_store_keeps_title_roles_separate_and_persistent(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / "data"
            source = Path(folder) / "example.hwpx"
            _write_hwpx(source, number="", title="예시 제목")
            store = UserContentStore(root)

            document = store.add_auto_title_template(
                "document_title",
                "공통 이름",
                source,
                title_token=DOCUMENT_TITLE_TOKEN,
            )
            section = store.add_auto_title_template(
                "title",
                "공통 이름",
                source,
                title_token=SECTION_TITLE_TOKEN,
                number_token=SECTION_NUMBER_TOKEN,
            )

            duplicate_format = store.add_auto_title_template(
                "title",
                "같은 모양 두 번째",
                source,
                title_token=SECTION_TITLE_TOKEN,
                number_token=SECTION_NUMBER_TOKEN,
            )

            self.assertEqual(len(store.list_auto_title_templates("document_title")), 1)
            self.assertEqual(len(store.list_auto_title_templates("title")), 2)
            self.assertNotEqual(section["id"], duplicate_format["id"])
            with self.assertRaisesRegex(UserContentError, "같은 이름"):
                store.add_auto_title_template(
                    "title",
                    "공통 이름",
                    source,
                    title_token=SECTION_TITLE_TOKEN,
                    number_token=SECTION_NUMBER_TOKEN,
                )

            reloaded = UserContentStore(root)
            reloaded_titles = reloaded.list_auto_title_templates("title")
            self.assertEqual(len(reloaded_titles), 2)
            self.assertEqual(reloaded_titles[0]["id"], section["id"])
            self.assertEqual(reloaded_titles[1]["id"], duplicate_format["id"])
            copied = Path(
                reloaded.list_auto_title_templates("document_title")[0]["file"]
            )
            reloaded.delete_auto_title_template(document["id"])
            self.assertFalse(copied.exists())


if __name__ == "__main__":
    unittest.main()