#!/usr/bin/env python3
"""Impose a PDF as a two-up, saddle-stitched booklet."""

from __future__ import annotations

import argparse
import copy
import math
from pathlib import Path
from typing import Iterable

from pypdf import PdfReader, PdfWriter, Transformation


def booklet_spreads(page_count: int) -> list[tuple[int | None, int | None]]:
    """Return left/right zero-based source page indexes in print order.

    Every two returned spreads are the front and back of one physical sheet.
    ``None`` represents a blank page added to complete a four-page signature.
    """
    if page_count < 1:
        raise ValueError("The input PDF has no pages")
    padded = math.ceil(page_count / 4) * 4
    result: list[tuple[int | None, int | None]] = []
    low, high = 0, padded - 1
    while low < high:
        result.append((high if high < page_count else None, low if low < page_count else None))
        low += 1
        high -= 1
        result.append((low if low < page_count else None, high if high < page_count else None))
        low += 1
        high -= 1
    return result


def _place_page(output_page, source_page, x: float, slot_width: float, slot_height: float) -> None:
    page = copy.copy(source_page)
    if page.rotation:
        page.transfer_rotation_to_content()
    box = page.cropbox
    width, height = float(box.width), float(box.height)
    if width <= 0 or height <= 0:
        raise ValueError("A source page has an invalid page box")
    scale = min(slot_width / width, slot_height / height)
    dx = x + (slot_width - width * scale) / 2 - float(box.left) * scale
    dy = (slot_height - height * scale) / 2 - float(box.bottom) * scale
    output_page.merge_transformed_page(
        page,
        Transformation().scale(scale, scale).translate(dx, dy),
        over=True,
    )


def impose_booklet(input_path: Path, output_path: Path) -> None:
    reader = PdfReader(str(input_path))
    spreads = booklet_spreads(len(reader.pages))
    first = copy.copy(reader.pages[0])
    if first.rotation:
        first.transfer_rotation_to_content()
    source_width = float(first.cropbox.width)
    source_height = float(first.cropbox.height)
    # Keep the source paper stock, turned landscape. Each logical page is
    # reduced to one half of the physical sheet (Letter -> half-Letter, etc.).
    sheet_width = max(source_width, source_height)
    sheet_height = min(source_width, source_height)
    slot_width = sheet_width / 2
    writer = PdfWriter()

    for left_index, right_index in spreads:
        sheet = writer.add_blank_page(width=sheet_width, height=sheet_height)
        for index, x in ((left_index, 0.0), (right_index, slot_width)):
            if index is not None:
                _place_page(sheet, reader.pages[index], x, slot_width, sheet_height)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("wb") as stream:
        writer.write(stream)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Arrange a PDF two-up for hamburger-folded, nested booklet printing."
    )
    parser.add_argument("input", type=Path, help="PDF in normal reading order")
    parser.add_argument("output", type=Path, nargs="?", help="Output PDF (default: <name>-booklet.pdf)")
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    input_path = args.input.expanduser().resolve()
    if not input_path.is_file():
        raise SystemExit(f"Input PDF not found: {input_path}")
    output_path = (
        args.output.expanduser().resolve()
        if args.output
        else input_path.with_name(f"{input_path.stem}-booklet.pdf")
    )
    if output_path == input_path:
        raise SystemExit("Output path must be different from input path")
    impose_booklet(input_path, output_path)
    print(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
