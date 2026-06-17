"""Shared output file naming helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Optional


def normalize_output_format(value: Optional[str], fallback: str = "md") -> str:
    fmt = str(value or "").strip().lower().lstrip(".")
    aliases = {
        "markdown": "md",
        "text": "txt",
        "plaintext": "txt",
        "plain_text": "txt",
        "excel": "xlsx",
        "xls": "xlsx",
    }
    fmt = aliases.get(fmt, fmt)
    return fmt or fallback


def output_filename_from_source(source_name: str, output_format: Optional[str] = None) -> str:
    source = Path(str(source_name or "output")).name
    source_path = Path(source)
    ext = normalize_output_format(output_format or source_path.suffix, "md")
    return f"{source_path.stem}_out.{ext}"


def output_path_from_source(output_dir: str | Path, source_name: str, output_format: Optional[str] = None) -> Path:
    return Path(output_dir) / output_filename_from_source(source_name, output_format)
