"""Inspect exported PDF text/layout and make review sheets from Poppler renders."""
from pathlib import Path
import json
from PIL import Image, ImageDraw
from pypdf import PdfReader
import pdfplumber

root = Path(__file__).resolve().parents[2]
version = json.loads((root / "tauri-prototype/package.json").read_text(encoding="utf-8"))["version"]
pdf = root / f"매뉴얼/배포본/JBEdu_FORM_사용자매뉴얼_v.{version}.pdf"
reader = PdfReader(pdf)
texts = [page.extract_text() or "" for page in reader.pages]
assert all(text.strip() for text in texts), "Blank PDF page"
assert all(len(text.strip()) >= 150 for text in texts), "Isolated short text on a PDF page"
assert all("�" not in text for text in texts), "Broken PDF text encoding"
assert sum("01 처음 사용하기" in text for text in texts) == 1
assert sum("14 문제 해결" in text for text in texts) == 1
assert sum(text.count(f"v.{version}") for text in texts) == 1, "Repeated manual version"
with pdfplumber.open(pdf) as document:
    for page in document.pages:
        assert all(0 <= char["x0"] <= char["x1"] <= page.width + 1 for char in page.chars)
        assert all(0 <= char["top"] <= char["bottom"] <= page.height + 1 for char in page.chars)

folder = root / "매뉴얼/도구/검증결과"
for batch in range((len(texts) + 5) // 6):
    sheet = Image.new("RGB", (1530, 1460), "#dce2e6")
    draw = ImageDraw.Draw(sheet)
    for local in range(6):
        index = batch * 6 + local
        if index >= len(texts):
            break
        image = Image.open(folder / f"pdf-{index + 1:02d}.png").convert("RGB")
        image.thumbnail((490, 690))
        x = (local % 3) * 510 + 10
        y = (local // 3) * 730 + 25
        sheet.paste(image, (x, y))
        draw.text((x, y - 19), f"Page {index + 1}", fill="#202c38")
    sheet.save(folder / f"sheet-{batch + 1}.png")
print(f"PDF verified: {len(texts)} pages, text and page bounds intact.")
