import base64
import html
from io import BytesIO
from pathlib import Path

import pandas as pd
import streamlit as st
from PIL import Image, ImageOps

from src.caption_detect import GROUP_ONE_ENTRY
from src.caption_format import (
    build_formatted_source,
    clean_caption_cell,
    clean_page,
    format_number_group,
)

GROUP_STRATEGY_LABELS = {
    "composite": "One composite figure",
    "separate": "Separate figures",
}


@st.cache_data(show_spinner=False)
def image_preview(image_bytes, max_height=320):
    """Convert one image or a composite image group to a browser-ready data URL."""
    blobs = image_bytes if isinstance(image_bytes, (list, tuple)) else [image_bytes]
    images = []

    for blob in blobs:
        if not blob:
            continue
        try:
            with Image.open(BytesIO(bytes(blob))) as image:
                images.append(ImageOps.exif_transpose(image).convert("RGB"))
        except (OSError, ValueError):
            continue

    if not images:
        return None

    # Composite figures are rendered side by side; thumbnails stay lightweight.
    target_height = min(max(image.height for image in images), max_height)
    resized = [
        image.resize((max(1, round(image.width * target_height / image.height)), target_height))
        for image in images
    ]
    canvas = Image.new("RGB", (sum(image.width for image in resized), target_height), "white")
    offset = 0

    for image in resized:
        canvas.paste(image, (offset, 0))
        offset += image.width

    output = BytesIO()
    canvas.save(output, format="JPEG", quality=90, optimize=True)
    encoded = base64.b64encode(output.getvalue()).decode("ascii")
    return f"data:image/jpeg;base64,{encoded}"


def filter_rework_objects(df_images, df_tables, excluded_images=(), excluded_tables=()):
    """Exclude user-selected objects while preserving their Word object identifiers."""
    images = (
        df_images[~df_images["image_no"].isin(excluded_images)].copy()
        if not df_images.empty else df_images.copy()
    )
    tables = (
        df_tables[~df_tables["table_no"].isin(excluded_tables)].copy()
        if not df_tables.empty else df_tables.copy()
    )
    if not images.empty:
        images = images.sort_values("image_no")
        images["image_idx_in_paragraph"] = images.groupby("paragraph_idx").cumcount()
        images["images_in_paragraph"] = images.groupby("paragraph_idx")["image_no"].transform("size")
    return images, tables.sort_values("table_no") if not tables.empty else tables


def apply_group_strategies(df_images, strategies, default_strategy):
    """Attach one strategy to every multi-image paragraph; single images stay blank."""
    images = df_images.copy()
    images["group_strategy"] = None
    if images.empty:
        return images

    grouped = images["images_in_paragraph"].gt(1)
    selected = images.loc[grouped, "paragraph_idx"].map(strategies).fillna(default_strategy)
    images.loc[grouped, "group_strategy"] = selected
    return images


def table_preview(doc, table_idx, max_rows=2, max_columns=4):
    """Return a compact text preview of a Word table."""
    table = doc.tables[int(table_idx)]
    rows = []
    for row in table.rows[:max_rows]:
        cells = []
        for cell in row.cells[:max_columns]:
            text = " ".join(cell.text.split())
            cells.append(f"{text[:77]}..." if len(text) > 80 else text)
        rows.append(" | ".join(cells))
    return " / ".join(filter(None, rows)) or "Empty table"


def object_removal_editor(df_images, df_tables, doc, key_suffix):
    """Render object selectors and return removals plus corrected group strategies."""
    selected_images, selected_tables, strategies = [], [], {}

    if not df_images.empty:
        image_rows = df_images[
            ["image_no", "paragraph_idx", "images_in_paragraph", "page", "image_bytes", "group_strategy"]
        ].copy().reset_index(drop=True)
        image_rows.insert(0, "remove", False)
        image_rows["preview"] = image_rows["image_bytes"].apply(image_preview)
        image_rows["grouped_images"] = image_rows["group_strategy"].map(GROUP_STRATEGY_LABELS)
        edited = st.data_editor(
            image_rows[["remove", "image_no", "page", "grouped_images", "preview"]],
            width="stretch", hide_index=True, disabled=["image_no", "page", "preview"],
            column_config={
                "remove": st.column_config.CheckboxColumn("Remove"),
                "image_no": st.column_config.NumberColumn("Image"),
                "page": st.column_config.NumberColumn("Page"),
                "grouped_images": st.column_config.SelectboxColumn(
                    "Grouped images", options=list(GROUP_STRATEGY_LABELS.values()),
                    help="For image groups only. Changing any row updates the whole group.",
                ),
                "preview": st.column_config.ImageColumn("Preview (Double click to make larger)", width="small"),
            },
            key=f"rework_image_selector_{key_suffix}",
        )
        selected_images = edited.loc[edited["remove"], "image_no"].astype(int).tolist()
        reverse_labels = {label: strategy for strategy, label in GROUP_STRATEGY_LABELS.items()}
        for paragraph_idx, group in image_rows[image_rows["images_in_paragraph"].gt(1)].groupby("paragraph_idx"):
            current = GROUP_STRATEGY_LABELS[group.iloc[0]["group_strategy"]]
            values = edited.loc[group.index, "grouped_images"].dropna().tolist()
            changed = [value for value in values if value != current]
            strategies[int(paragraph_idx)] = reverse_labels[changed[-1] if changed else current]

    if not df_tables.empty:
        table_rows = df_tables[["table_no", "table_idx", "page"]].copy()
        table_rows.insert(0, "remove", False)
        table_rows["preview"] = table_rows["table_idx"].apply(lambda index: table_preview(doc, index))
        edited = st.data_editor(
            table_rows[["remove", "table_no", "page", "preview"]],
            width="stretch", hide_index=True, disabled=["table_no", "page", "preview"],
            column_config={
                "remove": st.column_config.CheckboxColumn("Remove"),
                "table_no": st.column_config.NumberColumn("Table"),
                "page": st.column_config.NumberColumn("Page"),
                "preview": st.column_config.TextColumn("Content preview"),
            },
            key=f"rework_table_selector_{key_suffix}",
        )
        selected_tables = edited.loc[edited["remove"], "table_no"].astype(int).tolist()

    return selected_images, selected_tables, strategies


CAPTION_DISPLAY_COLUMNS = [
    "image_no",
    "page",
    "text",
    "source",
    "image_preview",
    "caption_status",
    "label_status",
]

READ_ONLY_CAPTION_COLUMNS = [
    "image_no",
    "page",
    "image_preview",
    "caption_status",
    "label_status",
]

TABLE_DISPLAY_COLUMNS = [
    "table_preview",
    "label",
    "text",
    "source",
    "table_no",
    "page",
    "caption_status",
    "label_status",
]

READ_ONLY_TABLE_COLUMNS = [
    "table_preview",
    "label",
    "table_no",
    "page",
    "caption_status",
    "label_status",
]


def needs_manual_attention(row):
    return (
        row["caption_status"] != "found_by_label"
        or row["label_status"] != "found_label"
    )


def highlight_attention_rows(row):
    if needs_manual_attention(row):
        return ["background-color: #D0311E"] * len(row)

    return [""] * len(row)


def highlight_ai_rows(row):
    """Distinguish AI edits from suggestions that still require manual work."""
    if row.get("edit_type") == "UNRESOLVED":
        return ["background-color: #D0311E"] * len(row)
    if row.get("decision") == "EDIT":
        return ["background-color: #F2C14E"] * len(row)
    return [""] * len(row)


def merge_list_edits(source, edited):
    """Merge visible editor columns back into rows containing hidden AI metadata."""
    result = source.copy().reset_index(drop=True)
    for column in edited.columns:
        result[column] = edited[column].tolist()
    return result


def caption_display_df(df):
    display_df = df.copy()
    if "image_bytes" in display_df:
        display_df["image_preview"] = display_df["image_bytes"].apply(image_preview)

    for column in CAPTION_DISPLAY_COLUMNS:
        if column not in display_df.columns:
            display_df[column] = ""

    return display_df[CAPTION_DISPLAY_COLUMNS]


def table_caption_display_df(df):
    display_df = df.copy()

    for column in TABLE_DISPLAY_COLUMNS:
        if column not in display_df.columns:
            display_df[column] = ""

    return display_df[TABLE_DISPLAY_COLUMNS]


def merge_caption_edits(df_captions, edited_captions):
    accepted_captions = df_captions.copy()

    for column in ["text", "source"]:
        accepted_captions[column] = edited_captions[column]

    return accepted_captions


def caption_part_style(settings, part):
    return (
        f"font-family: '{settings['font_name']}', serif;"
        f"font-size: {settings['font_size']}px;"
        f"font-weight: {'700' if settings[f'{part}_bold'] else '400'};"
        f"font-style: {'italic' if settings[f'{part}_italic'] else 'normal'};"
    )


def image_count(row):
    try:
        return int(row["images_in_paragraph"])
    except (TypeError, ValueError):
        return 1


def image_group_strategy(row, settings):
    strategy = row.get("group_strategy")
    return strategy if strategy in GROUP_STRATEGY_LABELS else settings["multi_image_strategy"]


def build_number_part(caption_number, row, settings):
    images_count = image_count(row)
    numbers = list(range(caption_number, caption_number + images_count))

    if images_count > 1 and image_group_strategy(row, settings) == "separate":
        return format_number_group(
            numbers,
            settings["multi_number_separator"],
        )

    return str(caption_number)


def build_changed_captions(accepted_captions, settings):
    rows = []
    caption_number = 1

    for _, row in accepted_captions.iterrows():
        number_part = build_number_part(caption_number, row, settings)
        caption_text = clean_caption_cell(row["text"])
        source_text = clean_caption_cell(row["source"])

        rows.append({
            "object_type": "figure",
            "object_paragraph_idx": row.get("paragraph_idx"),
            "caption_paragraph_idx": row["caption_paragraph_idx"],
            "page": clean_page(row.get("page")),
            "caption_label": settings["caption_label"],
            "new_number": number_part,
            "caption_text": caption_text,
            "source_text": source_text,
            "label": f"{settings['caption_label']} {number_part}.",
            "text": caption_text,
            "source": build_formatted_source(source_text, settings),
        })

        if image_count(row) > 1 and image_group_strategy(row, settings) == "separate":
            caption_number += image_count(row)
        else:
            caption_number += 1

    return rows


def build_changed_table_captions(accepted_captions, settings):
    rows = []
    for caption_number, (_, row) in enumerate(accepted_captions.iterrows(), start=1):
        caption_text = clean_caption_cell(row["text"])
        source_text = clean_caption_cell(row["source"])
        number_part = str(caption_number)

        rows.append({
            "object_type": "table",
            "table_idx": row.get("table_idx"),
            "table_caption_position": row.get("table_caption_position"),
            "caption_paragraph_idx": row["caption_paragraph_idx"],
            "source_paragraph_idx": row.get("source_paragraph_idx"),
            "page": clean_page(row.get("page")),
            "caption_label": settings["table_caption_label"],
            "new_number": number_part,
            "caption_text": caption_text,
            "source_text": source_text,
            "label": f"{settings['table_caption_label']} {number_part}.",
            "text": caption_text,
            "source": build_formatted_source(source_text, settings),
        })

    return rows


def output_file_name(file_name):
    path = Path(file_name)

    return f"{path.stem}_captions.docx"


def refreshed_output_file_name(file_name):
    path = Path(file_name)

    return f"{path.stem}_lists_refreshed.docx"


def build_refresh_group_decisions(df_captions):
    """Return one editable mapping decision for every multi-image paragraph."""
    columns = [
        "group_id", "images", "detected_caption", "detected_numbers",
        "treatment", "image_preview",
    ]
    groups = df_captions[df_captions["images_in_paragraph"].gt(1)]

    if groups.empty:
        return pd.DataFrame(columns=columns)

    rows = []
    for paragraph_idx, group in groups.groupby("paragraph_idx", sort=False):
        first = group.iloc[0]
        rows.append({
            "group_id": int(paragraph_idx),
            "images": len(group),
            "detected_caption": first["detected_caption"],
            "detected_numbers": first["detected_numbers"],
            "treatment": first["suggested_treatment"],
            "image_preview": image_preview(group["image_bytes"].tolist()),
        })

    return pd.DataFrame(rows, columns=columns)


def build_refresh_figure_rows(df_captions, decisions, settings):
    """Expand groups according to user decisions and renumber the resulting list."""
    decision_by_group = (
        decisions.set_index("group_id")["treatment"].to_dict()
        if decisions is not None and not decisions.empty
        else {}
    )
    rows = []

    for paragraph_idx, group in df_captions.groupby("paragraph_idx", sort=False):
        group = group.sort_values("image_idx_in_paragraph")
        treatment = decision_by_group.get(int(paragraph_idx), "Single")
        selected = [group.iloc[0]] if treatment == GROUP_ONE_ENTRY else [row for _, row in group.iterrows()]

        group_id = f"refresh-{paragraph_idx}" if len(selected) > 1 else None
        for group_index, row in enumerate(selected, start=1):
            rows.append({
                "status": "Multiple images" if len(group) > 1 else "Single image",
                "text": clean_caption_cell(row["text"]),
                "page": clean_page(row.get("page")),
                "image_bytes": group["image_bytes"].tolist() if treatment == GROUP_ONE_ENTRY else row["image_bytes"],
                "_ai_group_id": group_id,
                "_ai_group_index": group_index,
            })

    result = pd.DataFrame(
        rows,
        columns=["status", "text", "page", "image_bytes", "_ai_group_id", "_ai_group_index"],
    )
    result.insert(1, "label", [
        f"{settings['caption_label']} {number}."
        for number in range(1, len(result) + 1)
    ])
    return result


def build_refresh_table_rows(df_captions, settings):
    """Create sequential list rows from detected table captions."""
    result = df_captions[["table_idx", "text", "page"]].copy()
    result["text"] = result["text"].apply(clean_caption_cell)
    result["page"] = result["page"].apply(clean_page)
    result.insert(0, "label", [
        f"{settings['table_caption_label']} {number}."
        for number in range(1, len(result) + 1)
    ])
    return result


def _page_lookup(page_map):
    if page_map is None or page_map.empty:
        return {}
    return dict(zip(page_map["index"].astype(int), page_map["page"]))


def _image_nos(row):
    value = row.get("image_nos")
    if isinstance(value, (list, tuple)):
        return [int(number) for number in value]
    value = row.get("image_no")
    if isinstance(value, str):
        return [int(number.strip()) for number in value.split(",") if number.strip().isdigit()]
    try:
        return [int(value)]
    except (TypeError, ValueError):
        return []


def build_figure_list_rows(accepted_captions, settings, page_map=None):
    """Build final figure-list rows, optionally using freshly detected Word pages."""
    rows = []
    caption_number = 1
    pages = _page_lookup(page_map)

    for source_index, (_, row) in enumerate(accepted_captions.iterrows(), start=1):
        text = clean_caption_cell(row["text"])
        images_count = image_count(row)
        image_nos = _image_nos(row)
        fallback_page = clean_page(row.get("page"))

        if images_count > 1 and image_group_strategy(row, settings) == "separate":
            for offset in range(images_count):
                image_no = image_nos[offset] if offset < len(image_nos) else None
                rows.append({
                    "label": f"{settings['caption_label']} {caption_number + offset}.",
                    "text": text,
                    "page": clean_page(pages.get(image_no, fallback_page)),
                    "image_bytes": row["image_bytes"][offset],
                    "_ai_group_id": f"full-{source_index}",
                    "_ai_group_index": offset + 1,
                })
            caption_number += images_count
        else:
            image_no = image_nos[0] if image_nos else None
            rows.append({
                "label": f"{settings['caption_label']} {caption_number}.",
                "text": text,
                "page": clean_page(pages.get(image_no, fallback_page)),
                "image_bytes": row["image_bytes"],
                "_ai_group_id": None,
                "_ai_group_index": 1,
            })
            caption_number += 1

    return pd.DataFrame(
        rows,
        columns=[
            "label", "text", "page", "image_bytes", "_ai_group_id", "_ai_group_index",
        ],
    )


def build_table_list_rows(accepted_captions, settings, page_map=None):
    """Build final table-list rows, optionally using freshly detected Word pages."""
    rows = []
    pages = _page_lookup(page_map)

    for caption_number, (_, row) in enumerate(accepted_captions.iterrows(), start=1):
        try:
            table_no = int(row.get("table_no"))
        except (TypeError, ValueError):
            table_no = None
        rows.append({
            "label": f"{settings['table_caption_label']} {caption_number}.",
            "text": clean_caption_cell(row["text"]),
            "page": clean_page(pages.get(table_no, row.get("page"))),
            "table_idx": row.get("table_idx"),
        })

    return pd.DataFrame(rows, columns=["label", "text", "page", "table_idx"])


def render_changed_captions(changed_captions, settings):
    label_style = caption_part_style(settings, "label")
    text_style = caption_part_style(settings, "text")
    source_style = caption_part_style(settings, "source")

    rows_html = []
    for caption in changed_captions:
        rows_html.append(
            "<tr>"
            f"<td style=\"border-bottom:1px solid #eee; padding:8px;\"><span style=\"{label_style}\">{html.escape(caption['label'])}</span></td>"
            f"<td style=\"border-bottom:1px solid #eee; padding:8px;\"><span style=\"{text_style}\">{html.escape(caption['text'])}</span></td>"
            f"<td style=\"border-bottom:1px solid #eee; padding:8px;\"><span style=\"{source_style}\">{html.escape(caption['source'])}</span></td>"
            "</tr>"
        )

    table_html = f"""
    <table style="width:100%; border-collapse:collapse;">
        <thead>
            <tr>
                <th style="text-align:left; border-bottom:1px solid #ddd; padding:8px;">label</th>
                <th style="text-align:left; border-bottom:1px solid #ddd; padding:8px;">text</th>
                <th style="text-align:left; border-bottom:1px solid #ddd; padding:8px;">source</th>
            </tr>
        </thead>
        <tbody>
            {''.join(rows_html)}
        </tbody>
    </table>
    """

    st.markdown(table_html, unsafe_allow_html=True)
