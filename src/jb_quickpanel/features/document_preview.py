# -*- coding: utf-8 -*-
import io
import zipfile
from pathlib import Path

from PIL import Image, ImageChops

from src.jb_quickpanel.vendor import olefile


_HWP_PREVIEW_STREAM = "PrvImage"
_HWPX_PREVIEW_NAMES = (
    "preview/prvimage.png",
    "preview/prvimage.jpg",
    "preview/prvimage.jpeg",
    "preview/prvimage.bmp",
    "prvimage.png",
    "prvimage.jpg",
)


def _read_hwp_preview(source):
    if not olefile.isOleFile(str(source)):
        return None
    with olefile.OleFileIO(str(source)) as document:
        if not document.exists(_HWP_PREVIEW_STREAM):
            return None
        data = document.openstream(_HWP_PREVIEW_STREAM).read()
        return data if data else None


def _read_hwpx_preview(source):
    if not zipfile.is_zipfile(source):
        return None
    with zipfile.ZipFile(source) as document:
        names = {name.replace("\\", "/").lower(): name for name in document.namelist()}
        for candidate in _HWPX_PREVIEW_NAMES:
            actual = names.get(candidate)
            if actual:
                data = document.read(actual)
                return data if data else None
        for normalized, actual in names.items():
            if "/prvimage." in normalized or normalized.startswith("prvimage."):
                data = document.read(actual)
                return data if data else None
    return None


def _content_crop(image):
    rgb = image.convert("RGB")
    white = Image.new("RGB", rgb.size, "white")
    difference = ImageChops.difference(rgb, white).convert("L")
    mask = difference.point(lambda value: 255 if value > 18 else 0)
    box = mask.getbbox()
    if box is None:
        return rgb
    left, top, right, bottom = box
    padding_x = max(12, int((right - left) * 0.05))
    padding_y = max(12, int((bottom - top) * 0.08))
    return rgb.crop((
        max(0, left - padding_x),
        max(0, top - padding_y),
        min(rgb.width, right + padding_x),
        min(rgb.height, bottom + padding_y),
    ))


def create_document_preview(source_path, output_path, *, crop_content=False):
    source = Path(source_path)
    output = Path(output_path)
    if not source.is_file():
        return False, "미리보기를 만들 한글 파일을 찾지 못했습니다."

    try:
        extension = source.suffix.lower()
        if extension == ".hwp":
            data = _read_hwp_preview(source)
        elif extension == ".hwpx":
            data = _read_hwpx_preview(source)
        else:
            return False, "HWP 또는 HWPX 파일만 미리보기를 만들 수 있습니다."
        if not data:
            return False, "한글 파일 안에 저장된 미리보기 이미지를 찾지 못했습니다."

        with Image.open(io.BytesIO(data)) as image:
            preview = _content_crop(image) if crop_content else image.convert("RGB")
            preview.thumbnail((1000, 1400), Image.Resampling.LANCZOS)
            output.parent.mkdir(parents=True, exist_ok=True)
            preview.save(output, format="PNG", optimize=True)
        if not output.is_file() or output.stat().st_size <= 0:
            return False, "생성된 미리보기 파일을 확인하지 못했습니다."
        return True, str(output)
    except Exception as error:
        return False, f"미리보기 자동 생성 실패: {error}"
