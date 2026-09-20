"""Shared caption formatting for the UI and DOCX output."""

import pandas as pd


def clean_caption_cell(value):
    """Normalize a scalar editor value without writing missing-value markers."""
    if value is None or pd.isna(value):
        return ""
    text = str(value).strip()
    return "" if text.lower() in {"nan", "none", "<na>"} else text


def clean_page(value):
    """Return a usable page number, or an empty cell for invalid input."""
    text = clean_caption_cell(value)
    try:
        page = int(float(text))
    except (ValueError, OverflowError):
        return ""
    return page if 1 <= page <= 999999 else ""


def build_formatted_source(source, settings):
    source = clean_caption_cell(source)
    if not source:
        return ""
    text = f"{settings['source_label']} {source}"
    return f"({text})" if settings["source_in_parentheses"] else text


def format_number_group(numbers, separator):
    if len(numbers) == 1:
        return str(numbers[0])
    if separator == "\u2013":
        return f"{numbers[0]}\u2013{numbers[-1]}"
    joiner = ", " if separator == "," else f" {separator} "
    return joiner.join(map(str, numbers))
