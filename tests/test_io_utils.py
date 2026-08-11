from __future__ import annotations

from pathlib import Path

from aimatting.core.io_utils import (
    build_output_path,
    ensure_supported_suffix,
    is_supported,
    output_extension,
)


def test_is_supported() -> None:
    assert is_supported("a.jpg")
    assert is_supported("a.tiff")
    assert is_supported("a.webp")
    assert not is_supported("a.txt")


def test_output_extension() -> None:
    assert output_extension("png") == ".png"
    assert output_extension("jpg") == ".jpg"
    assert output_extension("jpeg") == ".jpg"
    assert output_extension("webp") == ".webp"


def test_build_output_path() -> None:
    out = build_output_path("C:/photos/photo.png", "C:/out", "抠图后", "png")
    assert out == Path("C:/out/photo抠图后.png")


def test_build_output_path_default_dir() -> None:
    out = build_output_path("C:/photos/photo.JPG", None, "抠图后", "webp")
    assert out == Path("C:/photos/photo抠图后.webp")


def test_suffix_cleaning() -> None:
    assert ensure_supported_suffix("抠图后") == "抠图后"
    assert ensure_supported_suffix("抠图后.png") == "抠图后"
    assert ensure_supported_suffix("  ") == ""
