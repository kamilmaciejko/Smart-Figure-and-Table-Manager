import json
import os
import subprocess
import sys
import tempfile

import pandas as pd

WD_DO_NOT_SAVE_CHANGES = 0
WD_STATISTIC_PAGES = 2
WD_ACTIVE_END_PAGE_NUMBER = 3
INLINE_IMAGE_TYPES = {3, 4}
FLOATING_IMAGE_TYPES = {11, 13}


class WordPageDetectionError(RuntimeError):
    """Raised when Microsoft Word cannot provide physical page numbers."""


def _physical_page(document, object_range, use_start=False):
    position = object_range.Start if use_start else object_range.End

    # Information(3) returns the physical page and ignores section numbering resets.
    try:
        page = document.Range(position, position).Information(WD_ACTIVE_END_PAGE_NUMBER)
        if page and int(page) > 0:
            return int(page)
    except Exception:
        pass

    # Preserve the proven method as a fallback for unusual Word documents.
    page = document.Range(0, max(position, 1)).ComputeStatistics(WD_STATISTIC_PAGES)
    return int(page) if page else None


def _image_ranges(document):
    inline = [
        document.InlineShapes(index).Range
        for index in range(1, document.InlineShapes.Count + 1)
        if document.InlineShapes(index).Type in INLINE_IMAGE_TYPES
    ]
    floating = [
        document.Shapes(index).Anchor
        for index in range(1, document.Shapes.Count + 1)
        if document.Shapes(index).Type in FLOATING_IMAGE_TYPES
    ]
    return sorted(inline + floating, key=lambda item: item.Start)


def _detect_object_pages_file(docx_path):
    """Run Word COM in the worker process and return serializable page rows."""
    try:
        import pythoncom
        import win32com.client
    except ImportError as exc:
        raise WordPageDetectionError(
            "Page detection requires pywin32 and a local Microsoft Word installation."
        ) from exc

    word = document = None
    com_initialized = False
    stage = "initializing COM"

    try:
        pythoncom.CoInitialize()
        com_initialized = True
        stage = "starting Microsoft Word"
        word = win32com.client.DispatchEx("Word.Application")
        word.Visible = False
        word.DisplayAlerts = 0
        try:
            word.Options.Pagination = True
        except Exception:
            pass

        stage = "opening the document"
        document = word.Documents.Open(
            os.path.abspath(docx_path), ReadOnly=True, AddToRecentFiles=False, Visible=False
        )

        # Repagination may fail when Word cannot access a stale printer login session.
        try:
            document.Repaginate()
        except Exception:
            pass

        stage = "reading object pages"
        image_rows = [
            {"index": index, "page": _physical_page(document, object_range)}
            for index, object_range in enumerate(_image_ranges(document), start=1)
        ]
        table_rows = [
            {
                "index": index,
                "page": _physical_page(document, document.Tables(index).Range, use_start=True),
            }
            for index in range(1, document.Tables.Count + 1)
        ]
        return {"images": image_rows, "tables": table_rows}
    except Exception as exc:
        raise WordPageDetectionError(
            f"Word object page detection failed while {stage}: {exc}"
        ) from exc
    finally:
        if document is not None:
            try:
                document.Close(WD_DO_NOT_SAVE_CHANGES)
            except Exception:
                pass
        if word is not None:
            try:
                word.Quit()
            except Exception:
                pass
        if com_initialized:
            try:
                pythoncom.CoUninitialize()
            except Exception:
                pass


def _run_page_worker(docx_bytes):
    temp_path = None

    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as temp_file:
            temp_file.write(docx_bytes)
            temp_path = temp_file.name

        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        result = subprocess.run(
            [sys.executable, os.path.abspath(__file__), temp_path],
            capture_output=True, text=True, encoding="utf-8", env=env, timeout=180,
        )

        if result.returncode:
            raise WordPageDetectionError(
                result.stderr.strip() or "Word page detection worker failed."
            )

        return json.loads(result.stdout)
    except WordPageDetectionError:
        raise
    except Exception as exc:
        raise WordPageDetectionError(f"Word page detection worker failed: {exc}") from exc
    finally:
        if temp_path:
            try:
                os.unlink(temp_path)
            except OSError:
                pass


def detect_object_pages(docx_bytes, expected_images=None, expected_tables=None):
    """Return validated image and table pages from one isolated Word session."""
    rows = _run_page_worker(docx_bytes)
    page_maps = {
        "images": pd.DataFrame(rows["images"], columns=["index", "page"]),
        "tables": pd.DataFrame(rows["tables"], columns=["index", "page"]),
    }
    for object_type, expected in (("images", expected_images), ("tables", expected_tables)):
        if expected is None:
            continue
        page_map = page_maps[object_type]
        valid = (
            len(page_map) == expected
            and page_map["index"].tolist() == list(range(1, expected + 1))
            and page_map["page"].notna().all()
            and page_map["page"].ge(1).all()
        )
        if not valid:
            raise WordPageDetectionError(
                f"The {object_type} returned by Word do not match the DOCX XML scan."
            )
    return page_maps


def _worker():
    try:
        print(json.dumps(_detect_object_pages_file(sys.argv[1])))
        return 0
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(_worker())
