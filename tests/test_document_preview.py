import io
import tempfile
import unittest
import zipfile
from pathlib import Path

from PIL import Image, ImageDraw

from src.jb_quickpanel.features import document_preview


ROOT = Path(__file__).resolve().parents[1]


class DocumentPreviewTests(unittest.TestCase):
    def test_content_crop_reduces_blank_page_margins(self):
        image = Image.new("RGB", (600, 800), "white")
        draw = ImageDraw.Draw(image)
        draw.rectangle((180, 260, 420, 520), fill="black")

        cropped = document_preview._content_crop(image)

        self.assertLess(cropped.width, image.width)
        self.assertLess(cropped.height, image.height)

    def test_real_hwp_embedded_preview_is_written_without_opening_hwp(self):
        source = ROOT / "blocks_hwp" / "참고박스.hwp"
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "preview.png"

            ok, _message = document_preview.create_document_preview(
                source, output, crop_content=True
            )

            self.assertTrue(ok)
            with Image.open(output) as image:
                self.assertEqual(image.format, "PNG")
                self.assertGreater(image.width, 0)
                self.assertGreater(image.height, 0)

    def test_hwpx_preview_package_is_supported(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "source.hwpx"
            output = Path(folder) / "preview.png"
            buffer = io.BytesIO()
            Image.new("RGB", (200, 280), "white").save(buffer, format="PNG")
            with zipfile.ZipFile(source, "w") as package:
                package.writestr("Preview/PrvImage.png", buffer.getvalue())

            ok, _message = document_preview.create_document_preview(source, output)

            self.assertTrue(ok)
            with Image.open(output) as image:
                self.assertEqual(image.size, (200, 280))


if __name__ == "__main__":
    unittest.main()
