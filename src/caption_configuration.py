import streamlit as st

from src.caption_format import build_formatted_source, format_number_group

LANGUAGES = ["Polish", "English"]

CAPTION_LABELS = {
    "Polish": ["Rys.", "Rysunek"],
    "English": ["Fig.", "Figure"],
}

TABLE_LABELS = {
    "Polish": ["Tabela", "Tab."],
    "English": ["Table", "Tab."],
}

SOURCE_LABELS = {
    "Polish": "\u0179r\u00f3d\u0142o:",
    "English": "Source:",
}

NUMBER_SEPARATORS = {
    "Polish": ["i", "\u2013", ","],
    "English": ["and", "\u2013", ","],
}

MULTI_IMAGE_STRATEGIES = {
    "Treat as one composite figure": "composite",
    "Treat as separate figures": "separate",
}

TABLE_CAPTION_POSITIONS = {
    "Caption above": "caption_above",
    "Caption below": "caption_below",
    "Label above, source below": "label_above_source_below",
}

FONT_OPTIONS = [
    "Times New Roman",
    "Arial",
    "Calibri",
    "Aptos",
    "Cambria",
    "Verdana",
    "Georgia",
    "Garamond",
    "Courier New",
]

def _html_style(font_name, font_size, bold=False, italic=False):
    return (
        f"font-family: '{font_name}', serif;"
        f"font-size: {font_size}px;"
        f"font-weight: {'700' if bold else '400'};"
        f"font-style: {'italic' if italic else 'normal'};"
    )

def _source_part(caption_settings, sample_source="own elaboration"):
    return build_formatted_source(sample_source, caption_settings)

def _number_part(separator):
    return format_number_group([1, 2], separator)


def _configured_label(detected_label, options):
    detected = (detected_label or "").casefold().rstrip(".")
    return next(
        (option for option in options if option.casefold().rstrip(".") == detected),
        options[0],
    )

def _render_caption_line(caption_settings, label_part, text_part, source_part):
    label_style = _html_style(
        font_name=caption_settings["font_name"],
        font_size=caption_settings["font_size"],
        bold=caption_settings["label_bold"],
        italic=caption_settings["label_italic"],
    )
    text_style = _html_style(
        font_name=caption_settings["font_name"],
        font_size=caption_settings["font_size"],
        bold=caption_settings["text_bold"],
        italic=caption_settings["text_italic"],
    )
    source_style = _html_style(
        font_name=caption_settings["font_name"],
        font_size=caption_settings["font_size"],
        bold=caption_settings["source_bold"],
        italic=caption_settings["source_italic"],
    )

    st.markdown(
        f"""
        <div style="padding: 14px; border: 1px solid #ddd; border-radius: 8px; margin-bottom: 8px;">
            <span style="{label_style}">{label_part}</span>
            <span style="{text_style}">{text_part}</span>
            <span style="{source_style}">{source_part}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_standard_preview(caption_settings):
    _render_caption_line(
        caption_settings=caption_settings,
        label_part=f"{caption_settings['caption_label']} 1. ",
        text_part="Example caption text ",
        source_part=_source_part(caption_settings),
    )


def _render_group_preview(caption_settings):
    strategy = caption_settings["multi_image_strategy"]

    if strategy == "separate":
        numbers = _number_part(caption_settings["multi_number_separator"])
        caption_text = "Example grouped caption "
    else:
        numbers = "1"
        caption_text = "Example composite figure caption "

    _render_caption_line(
        caption_settings=caption_settings,
        label_part=f"{caption_settings['caption_label']} {numbers}. ",
        text_part=caption_text,
        source_part=_source_part(caption_settings),
    )


def _render_sample_table():
    st.markdown(
        """
        <table style="width: 100%; border-collapse: collapse; margin: 8px 0 12px 0;">
            <thead>
                <tr>
                    <th style="border: 1px solid #ddd; padding: 8px; text-align: left;">Metric</th>
                    <th style="border: 1px solid #ddd; padding: 8px; text-align: left;">Value</th>
                </tr>
            </thead>
            <tbody>
                <tr>
                    <td style="border: 1px solid #ddd; padding: 8px;">Accuracy</td>
                    <td style="border: 1px solid #ddd; padding: 8px;">0.94</td>
                </tr>
                <tr>
                    <td style="border: 1px solid #ddd; padding: 8px;">F1 score</td>
                    <td style="border: 1px solid #ddd; padding: 8px;">0.91</td>
                </tr>
            </tbody>
        </table>
        """,
        unsafe_allow_html=True,
    )


def _render_table_caption_preview(caption_settings):
    table_caption_position = caption_settings["table_caption_position"]
    table_label = f"{caption_settings['table_caption_label']} 1. "
    table_text = "Example table caption "
    source_part = _source_part(caption_settings)

    if table_caption_position == "caption_above":
        _render_caption_line(caption_settings, table_label, table_text, source_part)
        _render_sample_table()
        return

    if table_caption_position == "caption_below":
        _render_sample_table()
        _render_caption_line(caption_settings, table_label, table_text, source_part)
        return

    _render_caption_line(caption_settings, table_label, table_text, "")
    _render_sample_table()
    _render_caption_line(caption_settings, "", "", source_part)


def _render_caption_preview(caption_settings):
    st.caption("Standard caption")
    _render_standard_preview(caption_settings)

    st.caption("Multiple images in one paragraph")
    _render_group_preview(caption_settings)

    st.caption("Table caption")
    _render_table_caption_preview(caption_settings)


def _formatting_controls(title, key_prefix, default_bold=False):
    st.markdown(f"**{title}**")

    bold = st.checkbox(
        "Bold",
        value=default_bold,
        key=f"{key_prefix}_bold",
    )
    italic = st.checkbox(
        "Italic",
        value=False,
        key=f"{key_prefix}_italic",
    )

    return bold, italic


def get_caption_configuration():
    """
    Display caption configuration controls and return selected settings.
    """

    st.header("Caption configuration")

    language = st.selectbox(
        "Language",
        LANGUAGES,
        index=0,
        key="caption_language",
    )

    col1, col2 = st.columns(2)

    with col1:
        caption_label = st.selectbox(
            "Caption label",
            CAPTION_LABELS[language],
            index=0,
            key="caption_label",
        )

    with col2:
        source_label = SOURCE_LABELS[language]
        st.text_input(
            "Source label",
            value=source_label,
            disabled=True,
            key=f"source_label_{language}",
        )

    table_caption_label = st.selectbox(
        "Table caption label",
        TABLE_LABELS[language],
        index=0,
        key="table_caption_label",
    )

    col3, col4 = st.columns(2)

    with col3:
        font_name = st.selectbox(
            "Caption font",
            FONT_OPTIONS,
            index=0,
            key="caption_font_name",
        )

    with col4:
        font_size = st.number_input(
            "Font size",
            min_value=1,
            max_value=99,
            value=10,
            step=1,
            key="caption_font_size",
        )

    selected_table_position_label = st.selectbox(
        "Table caption position",
        list(TABLE_CAPTION_POSITIONS),
        index=0,
        key="table_caption_position",
    )
    table_caption_position = TABLE_CAPTION_POSITIONS[selected_table_position_label]

    st.subheader("Formatting")

    label_col, text_col, source_col = st.columns(3)

    with label_col:
        label_bold, label_italic = _formatting_controls(
            "Label + number",
            key_prefix="label",
            default_bold=True,
        )

    with text_col:
        text_bold, text_italic = _formatting_controls(
            "Caption text",
            key_prefix="text",
        )

    with source_col:
        source_bold, source_italic = _formatting_controls(
            "Source",
            key_prefix="source",
        )
        source_in_parentheses = st.checkbox(
            "Parenthesis",
            value=True,
            key="source_in_parentheses",
        )

    st.subheader("Ambiguous image groups")

    strategy_options = list(MULTI_IMAGE_STRATEGIES)
    selected_strategy_label = st.selectbox(
        "Default treatment for multiple images in one row",
        strategy_options,
        index=0,
        key="multi_image_strategy",
    )
    multi_image_strategy = MULTI_IMAGE_STRATEGIES[selected_strategy_label]
    st.caption("Individual image groups can be corrected on the object selection page.")

    separator_options = NUMBER_SEPARATORS[language]
    multi_number_separator = st.selectbox(
        "Number separator for separate figures",
        separator_options,
        index=0,
        key="multi_number_separator",
    )

    caption_settings = {
        "language": language,
        "font_name": font_name,
        "font_size": font_size,
        "caption_label": caption_label,
        "table_caption_label": table_caption_label,
        "table_caption_position": table_caption_position,
        "source_label": source_label,
        "source_in_parentheses": source_in_parentheses,
        "label_bold": label_bold,
        "label_italic": label_italic,
        "text_bold": text_bold,
        "text_italic": text_italic,
        "source_bold": source_bold,
        "source_italic": source_italic,
        "multi_image_strategy": multi_image_strategy,
        "multi_number_separator": multi_number_separator,
    }

    st.subheader("Live preview")
    _render_caption_preview(caption_settings)

    return caption_settings

# List of figures and tables refresh configuration
def refresh_configuration(language, workflow, labels=None, key_suffix=""):
    """Display refresh controls for both lists (0), figures (1) or tables (2)."""
    suffix = f"_{key_suffix}" if key_suffix else ""
    labels = labels or {}
    show_figures = workflow in (0, 1)
    show_tables = workflow in (0, 2)
    caption_label = _configured_label(labels.get("caption_label"), CAPTION_LABELS[language])
    table_caption_label = _configured_label(
        labels.get("table_caption_label"), TABLE_LABELS[language]
    )

    st.header("Refresh lists of tables and figures")
    st.markdown("Select the current caption layout to refresh the detected lists.")
    st.caption("Captions are matched near each object using the detected label and selected table position.")

    # Values detected from the document are shown for reference, not edited here.
    st.text_input("Detected language", value=language, disabled=True, key=f"refresh_language{suffix}")
    if show_figures:
        st.text_input("Detected figure label", value=caption_label, disabled=True, key=f"refresh_figure_label{suffix}")
    if show_tables:
        st.text_input("Detected table label", value=table_caption_label, disabled=True, key=f"refresh_table_label{suffix}")

    table_caption_position = TABLE_CAPTION_POSITIONS["Caption above"]
    if show_tables:
        st.subheader("Table captions")
        position_name = st.selectbox(
            "Table caption position", list(TABLE_CAPTION_POSITIONS), key=f"refresh_table_caption_position{suffix}",
        )
        table_caption_position = TABLE_CAPTION_POSITIONS[position_name]

    st.subheader("Caption style")
    font_col, size_col = st.columns(2)
    with font_col:
        font_name = st.selectbox("Caption font", FONT_OPTIONS, key=f"refresh_caption_font{suffix}")
    with size_col:
        font_size = st.number_input(
            "Font size", min_value=1, max_value=50, value=10, step=1, key=f"refresh_caption_size{suffix}",
        )

    return {
        "language": language,
        "font_name": font_name,
        "font_size": font_size,
        "caption_label": caption_label,
        "source_label": SOURCE_LABELS[language],
        "table_caption_label": table_caption_label,
        "table_caption_position": table_caption_position,
    }
