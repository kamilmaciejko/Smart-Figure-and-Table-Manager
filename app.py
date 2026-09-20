import hashlib
from io import BytesIO

import streamlit as st
from docx import Document

from src.ai_config import activate_configured_llm
from src.caption_configuration import get_caption_configuration
from src.full_rework import run_full_rework
from src.object_detect import (
    detect_list_of_figures,
    detect_list_of_tables,
    extract_images,
    extract_tables,
)
from src.refresh_workflow import run_refresh_workflow
from src.word_pages import WordPageDetectionError, detect_object_pages

FULL_REWORK = "Full Tables and Figures Rework"
REFRESH_LISTS = "Refresh List of Tables and Figures"
PAGE_DETECTION_VERSION = 10

WORKFLOW_DEFAULTS = {
    "approved_caption_settings": None,
    "accepted_captions": None,
    "accepted_table_captions": None,
    "caption_stage": "object_selection",
    "edited_docx_bytes": None,
    "edited_docx_name": None,
    "caption_edited_docx_bytes": None,
    "table_of_figures": None,
    "list_of_tables": None,
    "excluded_image_nos": [],
    "excluded_table_nos": [],
    "group_strategies": {},
    "pending_object_removal": None,
    "object_selection_version": 0,
    "approved_refresh_settings": None,
    "refresh_stage": "review",
    "df_final_refresh": None,
    "refresh_docx_bytes": None,
    "refresh_docx_name": None,
    "full_ai_version": 0,
    "refresh_ai_version": 0,
    "refresh_ai_figures": None,
    "refresh_ai_tables": None,
    "refresh_ai_signature": None,
    "ai_review_requested": False,
    "ai_request_in_progress": False,
}


def reset_workflow_state(workflow=None):
    for key, value in WORKFLOW_DEFAULTS.items():
        st.session_state[key] = value.copy() if isinstance(value, (list, dict)) else value
    st.session_state.workflow = workflow


def start_new_document():
    st.session_state.clear()
    st.rerun()


def request_ai_review():
    """Queue one review request and prevent duplicate provider calls."""
    if not st.session_state.get("ai_request_in_progress", False):
        st.session_state.ai_request_in_progress = True
        st.session_state.ai_review_requested = True


st.set_page_config(
    page_title="Automatically Reference Images and Tables",
    layout="wide",
)
st.title("Automatically Reference Images and Tables")

with st.sidebar:
    ai_request_in_progress = st.session_state.get("ai_request_in_progress", False)
    if st.button("Activate AI functions", width="stretch", disabled=ai_request_in_progress):
        st.session_state.ai_request_in_progress = True
        try:
            with st.spinner("Waiting for the LLM response..."):
                activation = activate_configured_llm()
            st.session_state.llm_activation = activation
            st.session_state.llm_runtime_config = activation.get("config")
        finally:
            st.session_state.ai_request_in_progress = False

    st.caption("Warning: activation sends a short test request and may consume tokens.")
    activation = st.session_state.get("llm_activation")
    if activation and activation["status"] == "llm_active":
        st.success(f"AI functions active\n\nModel: `{activation['model']}`")
        current_workflow = st.session_state.get("workflow")
        ai_ready = (
            current_workflow == FULL_REWORK
            and st.session_state.get("caption_stage") == "list_edit"
        ) or (
            current_workflow == REFRESH_LISTS
            and st.session_state.get("approved_refresh_settings") is not None
            and st.session_state.get("refresh_stage", "review") == "review"
        )
        st.markdown("### Available AI Functions")
        if ai_request_in_progress:
            button_help = "AI review is in progress. Wait for the updated list before running it again."
        elif ai_ready:
            button_help = "Run AI review on the currently displayed lists."
        else:
            button_help = (
                "Available while editing Lists of Tables and Figures in Full Rework "
                "or while reviewing lists in Refresh."
            )
        st.button(
            "Improve list captions",
            disabled=not ai_ready or ai_request_in_progress,
            on_click=request_ai_review,
            width="stretch",
            help=button_help,
        )
        st.caption(
            "Reviews list descriptions, removes unnecessary commentary and visual "
            "references, and proposes safe group splits."
        )
    elif activation:
        st.warning("No LLM response detected. Check the configuration in src/ai_config.py.")
        if activation.get("error"):
            st.caption(f"Details: {activation['error']}")

if st.session_state.get("uploaded_docx_bytes") is None:
    st.write("Upload a DOCX file to scan its figures, tables, captions, and existing lists.")
    uploaded_file = st.file_uploader(
        "Upload DOCX file", type="docx", accept_multiple_files=False
    )
    if uploaded_file is None:
        st.stop()
    if not uploaded_file.name.lower().endswith(".docx"):
        st.error("Invalid file format. Please upload a .docx file.")
        st.stop()

    uploaded_bytes = uploaded_file.getvalue()
    st.session_state.uploaded_docx_bytes = uploaded_bytes
    st.session_state.uploaded_docx_name = uploaded_file.name
    st.session_state.uploaded_file_signature = (
        uploaded_file.name,
        hashlib.sha256(uploaded_bytes).hexdigest(),
    )
    st.session_state.image_pages = None
    st.session_state.table_pages = None
    st.session_state.page_detection_version = PAGE_DETECTION_VERSION
    reset_workflow_state()
    st.rerun()

uploaded_bytes = st.session_state.uploaded_docx_bytes
file_name = st.session_state.uploaded_docx_name
file_signature = st.session_state.uploaded_file_signature

if st.session_state.get("page_detection_version") != PAGE_DETECTION_VERSION:
    st.session_state.image_pages = None
    st.session_state.table_pages = None
    st.session_state.page_detection_version = PAGE_DETECTION_VERSION
    reset_workflow_state()

try:
    doc = Document(BytesIO(uploaded_bytes))
    df_images = extract_images(doc)
    df_tables = extract_tables(doc)
    figure_list = detect_list_of_figures(doc)
    table_list = detect_list_of_tables(doc)
except Exception as error:
    st.error("The file could not be processed.")
    st.exception(error)
    if st.button("Upload another document"):
        start_new_document()
    st.stop()

if df_images.empty and df_tables.empty:
    st.warning("No images or tables have been found in the document.")
    if st.button("Upload another document"):
        start_new_document()
    st.stop()

pages_missing = (
    (not df_images.empty and st.session_state.get("image_pages") is None)
    or (not df_tables.empty and st.session_state.get("table_pages") is None)
)
if pages_missing:
    try:
        with st.spinner("Scanning object pages with Microsoft Word..."):
            pages = detect_object_pages(uploaded_bytes, len(df_images), len(df_tables))
        st.session_state.image_pages = pages["images"]
        st.session_state.table_pages = pages["tables"]
    except WordPageDetectionError as error:
        st.error("Object page numbers could not be detected.")
        st.exception(error)
        if st.button("Upload another document"):
            start_new_document()
        st.stop()

if not df_images.empty:
    df_images = df_images.merge(
        st.session_state.image_pages,
        left_on="image_no", right_on="index", how="left",
    ).drop(columns="index")
if not df_tables.empty:
    df_tables = df_tables.merge(
        st.session_state.table_pages,
        left_on="table_no", right_on="index", how="left",
    ).drop(columns="index")

has_figure_heading = figure_list[1] is not None
has_table_heading = table_list[1] is not None
can_refresh = has_figure_heading or has_table_heading
workflow = st.session_state.get("workflow")

if workflow is None:
    st.header("Start Menu")
    st.success(f"Document scanned: {file_name}")
    image_col, table_col = st.columns(2)
    image_col.metric("Images", len(df_images))
    table_col.metric("Tables", len(df_tables))

    if figure_list[0]:
        st.success("A non-empty List of Figures was detected.")
    elif has_figure_heading:
        st.warning("A List of Figures heading was detected, but the list is empty.")
    else:
        st.caption("No existing List of Figures was detected.")

    if table_list[0]:
        st.success("A non-empty List of Tables was detected.")
    elif has_table_heading:
        st.warning("A List of Tables heading was detected, but the list is empty.")
    else:
        st.caption("No existing List of Tables was detected.")

    st.subheader("How do you need to rework your tables and figures?")
    full_col, refresh_col = st.columns(2)
    with full_col:
        if st.button(
            FULL_REWORK, width="stretch",
            help="Review objects, rebuild captions, and create lists of objects.",
        ):
            reset_workflow_state(FULL_REWORK)
            st.rerun()
    with refresh_col:
        if st.button(
            REFRESH_LISTS, width="stretch", disabled=not can_refresh,
            help="Refresh existing lists of objects.",
        ):
            reset_workflow_state(REFRESH_LISTS)
            st.rerun()

    if st.button("Upload another document"):
        start_new_document()
    st.stop()

top_left, top_right = st.columns([5, 1])
top_left.caption(f"Document: {file_name}")
with top_right:
    if st.button("Back to Start Menu", width="stretch"):
        reset_workflow_state()
        st.rerun()

if workflow == REFRESH_LISTS:
    run_refresh_workflow(
        doc, uploaded_bytes, file_name, file_signature,
        df_images, df_tables, figure_list, table_list,
    )
    st.stop()

settings = st.session_state.get("approved_caption_settings")
if settings is None:
    st.header("Full Rework: caption format")
    st.caption("Step 1 of 6")
    settings = get_caption_configuration()
    if st.button("Continue to object selection", type="primary"):
        st.session_state.approved_caption_settings = dict(settings)
        st.session_state.caption_stage = "object_selection"
        st.rerun()
    with st.expander("Current caption settings"):
        st.json(settings)
    st.stop()

run_full_rework(
    doc, uploaded_bytes, file_name, file_signature, df_images, df_tables,
    settings, has_figure_heading, has_table_heading,
)
