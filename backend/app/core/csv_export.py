"""Small helpers for building safe CSV downloads."""

from __future__ import annotations

import csv
import io
from collections.abc import Iterable, Sequence
from datetime import datetime

from fastapi.responses import Response

# Spreadsheet apps execute cells that start with these characters as formulas
# (CSV / formula injection, OWASP). Such cells are prefixed with a quote.
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def sanitize_cell(value) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, bool):
        return "yes" if value else "no"
    text = str(value)
    if text and text.startswith(_FORMULA_PREFIXES):
        # Plain negative numbers are harmless and common; keep them as numbers.
        if text.startswith("-") and text[1:].replace(".", "", 1).isdigit():
            return text
        return "'" + text
    return text


def build_csv(headers: Sequence[str], rows: Iterable[Sequence]) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(headers)
    for row in rows:
        writer.writerow([sanitize_cell(v) for v in row])
    return buf.getvalue()


def csv_response(filename: str, headers: Sequence[str], rows: Iterable[Sequence]) -> Response:
    # UTF-8 BOM so Excel opens non-ASCII names correctly
    body = "﻿" + build_csv(headers, rows)
    safe_name = "".join(c if c.isalnum() or c in "-_." else "_" for c in filename)
    return Response(
        content=body,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{safe_name}"'},
    )
