# -*- coding: utf-8 -*-
import os
import re


IMAGE_SIZE_FIT_INSIDE = "fit_inside"
IMAGE_SIZE_FIT_WIDTH = "fit_width"
IMAGE_SIZE_STRETCH_TO_CELL = "stretch_to_cell"
IMAGE_SIZE_MODES = (
    IMAGE_SIZE_FIT_INSIDE,
    IMAGE_SIZE_FIT_WIDTH,
    IMAGE_SIZE_STRETCH_TO_CELL,
)


def normalize_image_size_mode(mode: str) -> str:
    return mode if mode in IMAGE_SIZE_MODES else IMAGE_SIZE_FIT_INSIDE


def calculate_picture_size(mode, cell_width, cell_height, original_width, original_height):
    """현재 셀 안쪽 크기를 기준으로 그림의 HWPUNIT 크기를 계산한다."""
    mode = normalize_image_size_mode(mode)
    cell_width = max(1, int(cell_width))
    cell_height = max(1, int(cell_height))
    original_width = max(1, int(original_width))
    original_height = max(1, int(original_height))

    if mode == IMAGE_SIZE_STRETCH_TO_CELL:
        return cell_width, cell_height

    if mode == IMAGE_SIZE_FIT_WIDTH:
        width = cell_width
        height = max(1, round(width * original_height / original_width))
        return width, height

    scale = min(cell_width / original_width, cell_height / original_height)
    return (
        max(1, round(original_width * scale)),
        max(1, round(original_height * scale)),
    )


def natural_image_path_key(path: str):
    """그림1, 그림2, 그림10 순서가 되도록 파일명을 정렬한다."""
    name = os.path.basename(os.fspath(path)).casefold()
    return tuple(int(part) if part.isdigit() else part for part in re.split(r"(\d+)", name))


def sort_image_paths(paths):
    return sorted((os.path.abspath(os.fspath(path)) for path in paths), key=natural_image_path_key)
