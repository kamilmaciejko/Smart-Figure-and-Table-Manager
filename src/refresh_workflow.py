"""Streamlit workflow for refreshing existing lists of figures and tables."""

from io import BytesIO

import pandas as pd
import streamlit as st
from docx import Document

from src.ai_config import improve_list_rows
from src.caption_configuration import refresh_configuration
from src.caption_detect import (
    GROUP_ONE_ENTRY,
    GROUP_REVIEW_REQUIRED,
    GROUP_SEPARATE_ENTRIES,
    refresh_figures_caption_detect,
    refresh_tables_caption_detect,
)
from src.docx_edit import docx_to_bytes, replace_caption_lists
from src.ui_helpers import (
    build_refresh_figure_rows,
    build_refresh_group_decisions,
    build_refresh_table_rows,
    clean_caption_cell,
    clean_page,
    image_preview,
    highlight_ai_rows,
    merge_list_edits,
    refreshed_output_file_name,
    table_preview,
)


def _refresh_scope(figure_list, table_list):
    if figure_list[2] is not None and table_list[2] is not None:
        return figure_list[2], 0
    if figure_list[2] is not None:
        return figure_list[2], 1
    if table_list[2] is not None:
        return table_list[2], 2
    return None, 3


def _accepted_page(docx_bytes, file_name, settings, scope):
    final_rows = st.session_state.df_final_refresh
    st.header("Refresh: ready to download")
    st.caption("Step 3 of 3")

    for list_type, title in (("tables", "List of tables"), ("figures", "List of figures")):
        rows = final_rows[final_rows["list_type"] == list_type]
        if not rows.empty:
            st.subheader(title)
            st.dataframe(rows[["label", "text", "page"]], width="stretch", hide_index=True)

    if st.session_state.refresh_docx_bytes is None:
        figure_rows = final_rows[final_rows["list_type"] == "figures"]
        table_rows = final_rows[final_rows["list_type"] == "tables"]
        final_doc = replace_caption_lists(
            Document(BytesIO(docx_bytes)),
            figure_rows[["label", "text", "page"]],
            table_rows[["label", "text", "page"]],
            settings,
            replace_figures=scope in (0, 1),
            replace_tables=scope in (0, 2),
        )
        st.session_state.refresh_docx_bytes = docx_to_bytes(final_doc)
        st.session_state.refresh_docx_name = refreshed_output_file_name(file_name)

    back_col, download_col = st.columns(2)
    with back_col:
        if st.button("Back to list editing"):
            st.session_state.refresh_stage = "review"
            st.session_state.df_final_refresh = None
            st.session_state.refresh_docx_bytes = None
            st.session_state.refresh_docx_name = None
            st.rerun()
    with download_col:
        st.download_button(
            "Refresh and download",
            data=st.session_state.refresh_docx_bytes,
            file_name=st.session_state.refresh_docx_name,
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            type="primary",
        )


def _refresh_list_editor(rows, columns, disabled, key, column_config):
    """Render refresh rows with optional read-only AI comparison columns."""
    ai_result = "decision" in rows.columns
    visible = []
    for column in columns:
        if ai_result and column == "text":
            visible.append("original_text")
        visible.append(column)
    if ai_result:
        visible += ["decision", "edit_type"]
    display = rows[visible]
    if ai_result:
        display = display.style.apply(highlight_ai_rows, axis=1)
        disabled = [*disabled, "original_text", "decision", "edit_type"]
        column_config = {
            **column_config,
            "original_text": st.column_config.TextColumn("Original text"),
            "decision": st.column_config.TextColumn("AI decision"),
            "edit_type": st.column_config.TextColumn("Edit type"),
        }
    edited = st.data_editor(
        display, width="stretch", hide_index=True, disabled=disabled,
        column_config=column_config, key=key,
    )
    return merge_list_edits(rows, edited)


def _review_page(doc, df_images, df_tables, settings, scope, editor_key):
    st.header("Refresh: review lists")
    st.caption("Step 2 of 3")
    st.caption("Edit list text and resolve grouped figures before confirmation.")
    final_frames = []
    unresolved_groups = False
    missing_expected_entries = False
    summary = []
    edited_figures = pd.DataFrame()
    edited_tables = pd.DataFrame()
    decision_signature = "no-figures"
    ai_version = st.session_state.get("refresh_ai_version") or 0

    if scope in (0, 1):
        figures = refresh_figures_caption_detect(doc, df_images, settings)
        matched = figures["image_no"].nunique()
        groups = figures.loc[figures["images_in_paragraph"].gt(1), "paragraph_idx"].nunique()
        summary.append({
            "Object type": "Figures", "Detected": len(df_images),
            "Objects with captions": matched, "Not matched": len(df_images) - matched,
            "Image groups": groups,
        })
    else:
        figures = None

    if scope in (0, 2):
        tables = refresh_tables_caption_detect(doc, df_tables, settings)
        matched = tables["table_no"].nunique()
        summary.append({
            "Object type": "Tables", "Detected": len(df_tables),
            "Objects with captions": matched, "Not matched": len(df_tables) - matched,
            "Image groups": 0,
        })
    else:
        tables = None

    summary_df = pd.DataFrame(summary)
    st.subheader("Detection summary")
    st.dataframe(summary_df, width="stretch", hide_index=True)
    if not summary_df.empty and summary_df["Not matched"].gt(0).any():
        st.warning("Objects without matching captions will not be included in the refreshed lists.")

    if figures is not None:
        if figures.empty:
            st.error("No existing figure captions matched the detected label.")
            missing_expected_entries = True
        decisions = build_refresh_group_decisions(figures)
        if not decisions.empty:
            st.subheader("Grouped figures")
            st.caption("Choose one shared entry or one entry per image for every detected group.")
            edited_decisions = st.data_editor(
                decisions, width="stretch", hide_index=True,
                disabled=["group_id", "images", "detected_caption", "detected_numbers", "image_preview"],
                column_config={
                    "group_id": None,
                    "images": st.column_config.NumberColumn("Images"),
                    "detected_caption": st.column_config.TextColumn("Detected label"),
                    "detected_numbers": st.column_config.TextColumn("Numbers"),
                    "treatment": st.column_config.SelectboxColumn(
                        "Treatment",
                        options=[GROUP_ONE_ENTRY, GROUP_SEPARATE_ENTRIES, GROUP_REVIEW_REQUIRED],
                        required=True,
                    ),
                    "image_preview": st.column_config.ImageColumn("Preview", width="small"),
                },
                key=f"refresh_group_decisions_editor_{editor_key}",
            )
            unresolved_groups = edited_decisions["treatment"].eq(GROUP_REVIEW_REQUIRED).any()
        else:
            edited_decisions = decisions

        rows = build_refresh_figure_rows(figures, edited_decisions, settings)
        rows["image_preview"] = rows["image_bytes"].apply(image_preview)
        decision_signature = "-".join(edited_decisions["treatment"].astype(str)) or "single"
        ai_signature = f"{editor_key}_{decision_signature}"
        if (
            st.session_state.get("refresh_ai_signature") == ai_signature
            and st.session_state.get("refresh_ai_figures") is not None
        ):
            rows = st.session_state.refresh_ai_figures
        st.subheader("List of figures")
        edited_figures = _refresh_list_editor(
            rows, ["status", "label", "text", "page", "image_preview"],
            ["status", "label", "page", "image_preview"],
            f"refresh_captions_editor_{editor_key}_{decision_signature}_{ai_version}",
            {
                "status": st.column_config.TextColumn("Status"),
                "label": st.column_config.TextColumn("Label"),
                "text": st.column_config.TextColumn("Text"),
                "page": st.column_config.NumberColumn("Page"),
                "image_preview": st.column_config.ImageColumn("Image preview", width="small"),
            },
        )
        final_frames.append(edited_figures[["label", "text", "page"]].assign(list_type="figures"))

    if tables is not None:
        if tables.empty:
            st.error("No existing table captions matched the detected label and position.")
            missing_expected_entries = True
        rows = build_refresh_table_rows(tables, settings)
        rows["table_preview"] = rows["table_idx"].apply(lambda index: table_preview(doc, index))
        ai_signature = f"{editor_key}_{decision_signature}"
        if (
            st.session_state.get("refresh_ai_signature") == ai_signature
            and st.session_state.get("refresh_ai_tables") is not None
        ):
            rows = st.session_state.refresh_ai_tables
        st.subheader("List of tables")
        edited_tables = _refresh_list_editor(
            rows, ["label", "text", "page", "table_preview"],
            ["label", "page", "table_preview"],
            f"refresh_tables_editor_{editor_key}_{ai_version}",
            {
                "label": st.column_config.TextColumn("Label"),
                "text": st.column_config.TextColumn("Text"),
                "page": st.column_config.NumberColumn("Page"),
                "table_preview": st.column_config.TextColumn("Table preview"),
            },
        )
        final_frames.append(edited_tables[["label", "text", "page"]].assign(list_type="tables"))

    if st.session_state.pop("ai_review_requested", False):
        activation = st.session_state.get("llm_activation")
        config = st.session_state.get("llm_runtime_config")
        try:
            if not activation or activation.get("status") != "llm_active" or not config:
                st.error("AI functions not active.")
            else:
                with st.spinner("Reviewing list captions with AI..."):
                    ai_figures = improve_list_rows(
                        config, edited_figures, "figures", settings["language"]
                    )
                    ai_tables = improve_list_rows(
                        config, edited_tables, "tables", settings["language"]
                    )
                st.session_state.refresh_ai_figures = ai_figures
                st.session_state.refresh_ai_tables = ai_tables
                st.session_state.refresh_ai_signature = f"{editor_key}_{decision_signature}"
                st.session_state.refresh_ai_version = ai_version + 1
                st.rerun()
        except Exception as error:
            st.warning(f"AI caption review failed: {error}")
        finally:
            st.session_state.ai_request_in_progress = False

    final_rows = (
        pd.concat(final_frames, ignore_index=True)
        if final_frames else pd.DataFrame(columns=["label", "text", "page", "list_type"])
    )
    missing_text = not final_rows.empty and final_rows["text"].apply(clean_caption_cell).eq("").any()
    missing_page = not final_rows.empty and final_rows["page"].apply(clean_page).eq("").any()
    if unresolved_groups:
        st.error("Confirmation unavailable. There are grouped figures needing to be reviewed.")
    if missing_text:
        st.error("Confirmation unavailable. Every list entry must contain text.")
    if missing_page:
        st.error("Confirmation unavailable. Every list entry must have a valid page number.")

    unavailable = (
        unresolved_groups or missing_expected_entries or final_rows.empty
        or missing_text or missing_page
    )
    back_col, accept_col = st.columns(2)
    with back_col:
        if st.button("Back to refresh configuration"):
            st.session_state.approved_refresh_settings = None
            st.session_state.df_final_refresh = None
            st.session_state.refresh_ai_figures = None
            st.session_state.refresh_ai_tables = None
            st.session_state.refresh_ai_signature = None
            st.rerun()
    with accept_col:
        if st.button("Accept refreshed lists", type="primary", disabled=unavailable):
            st.session_state.df_final_refresh = final_rows
            st.session_state.refresh_docx_bytes = None
            st.session_state.refresh_docx_name = None
            st.session_state.refresh_stage = "accepted"
            st.rerun()


def run_refresh_workflow(
    doc, docx_bytes, file_name, file_signature, df_images, df_tables,
    figure_list, table_list,
):
    """Run the selected Refresh workflow without returning to the start menu."""
    if (
        figure_list[2] is not None and table_list[2] is not None
        and figure_list[2] != table_list[2]
    ):
        st.error("The detected lists use different languages and cannot be refreshed together.")
        return

    language, scope = _refresh_scope(figure_list, table_list)
    labels = {
        "caption_label": figure_list[3],
        "table_caption_label": table_list[3],
    }
    settings = st.session_state.get("approved_refresh_settings")
    if settings is None:
        st.header("Refresh: current caption format")
        st.caption("Step 1 of 3")
        config_key = file_signature[1][:12]
        settings = refresh_configuration(language, scope, labels, key_suffix=config_key)
        if st.button("Continue to list review", type="primary", key=f"confirm_refresh_{config_key}"):
            st.session_state.approved_refresh_settings = dict(settings)
            st.session_state.refresh_stage = "review"
            st.session_state.df_final_refresh = None
            st.session_state.refresh_docx_bytes = None
            st.session_state.refresh_docx_name = None
            st.rerun()
        return

    stage = st.session_state.get("refresh_stage", "review")
    if stage == "accepted":
        _accepted_page(docx_bytes, file_name, settings, scope)
        return

    key = f"v3_{file_signature[1][:12]}_{abs(hash(tuple(sorted(settings.items()))))}"
    _review_page(doc, df_images, df_tables, settings, scope, key)
