# Automatic Figure and Table Referencing

Have you ever finished a long report, only to discover that Figure 8 should be Figure 6, two tables use different caption styles, and the List of Figures is no longer correct?

I faced exactly this problem while writing my Master’s thesis. Keeping every figure, table, caption, source and page number consistent became a frustrating part of an already demanding project. I found Word functionalities not flexible and limited so decided to automate it and this app helped me bring order back to my thesis and focus on the actual work.

This local Streamlit app reviews figures and tables in Microsoft Word documents, helps correct and renumber their captions, and creates clean Lists of Figures and Tables. Optional AI support can improve list descriptions and save time, while every suggestion remains visible and editable before export.

Supported languages: 🇵🇱 Polish | 🇬🇧 English

| Option | What it does |
| --- | --- |
| **Full Tables and Figures Rework** | Reviews all detected objects, lets you exclude decorative items, correct captions and sources, apply one consistent style, renumber everything and create new lists. |
| **Refresh List of Tables and Figures** | Reads existing captions and lists, lets you correct their entries, and replaces outdated lists without rewriting body captions. |

The uploaded document is never overwritten. The result is downloaded as a new `.docx` file.

## 1. Technical overview

### Requirements and setup

Full document processing requires:

- Windows with desktop Microsoft Word installed and available in the current user session;
- Python 3.13 or newer;
- [uv](https://docs.astral.sh/uv/) for dependency management.

Clone or download the repository, open PowerShell in the project directory and run:

```powershell
uv sync --locked
uv run python -m streamlit run app.py --server.address localhost
```

Open the local address displayed in the terminal, usually `http://localhost:8501`.

### Project structure

```text
app.py                      Streamlit entry point and session state
pyproject.toml              Project metadata and direct dependencies
uv.lock                     Reproducible dependency versions
.python-version             Default Python version
.gitignore                  Excludes environments, secrets and DOCX files
.github/workflows/tests.yml GitHub Actions tests for Windows and Linux

src/
  object_detect.py          Detects document objects and existing lists
  caption_detect.py         Finds and parses nearby captions
  caption_format.py         Cleans text, sources, pages and number groups
  caption_configuration.py  Provides formatting controls and previews
  docx_edit.py              Writes captions and lists into DOCX files
  word_pages.py             Reads physical page numbers through Word
  full_rework.py            Controls the complete rework workflow
  refresh_workflow.py       Controls the list refresh workflow
  ui_helpers.py             Builds previews and editable data tables
  ai_config.py              Configures, calls and validates the LLM
  ai_prompts.py             Stores editable Polish and English AI prompts
  __init__.py               Marks src as a Python package

tests/
  test_ai_config.py         AI response validation and safe fallbacks
  test_ai_request_lock.py   Protection against duplicate AI requests
  test_app.py               End-to-end Streamlit workflow tests
  test_caption_format.py    Caption formatting tests
  test_docx_workflows.py    Synthetic DOCX editing and preservation tests
  test_ui_helpers.py        Preview and list-building tests
  test_word_pages.py        Page-map validation tests
  test_word_integration.py  Optional test with a real Word installation
```

### How it works

The app reads DOCX structure with `python-docx`, organizes detected objects and captions with `pandas`, and renders the workflow in Streamlit. Physical page numbers come from Microsoft Word through `pywin32`, because DOCX XML does not contain reliable rendered page positions.

Word runs in an isolated process. It opens a temporary copy in read-only mode, reads object pages, closes Word, and removes the temporary file. Returned object counts and page mappings are validated before they are used.

Caption and list editing is deterministic and works without AI. AI is limited to reviewing the text displayed in Lists of Figures and Tables. Invalid, incomplete or overlong responses are rejected, and the original description is retained as `UNRESOLVED`.

### Optional LLM configuration

Edit the user configuration block at the top of [`src/ai_config.py`](src/ai_config.py):

```python
provider = "ollama"
model = "qwen3.5:4b"
base_url = "http://localhost:11434/api/chat"
api_key = None
```

The defaults use a local Ollama server. You may select another provider supported by LiteLLM and adjust its model and endpoint. Keep `api_key = None` and provide hosted-provider credentials through environment variables rather than committing them to the repository.

The same file contains batch sizes, character limits, token limits and request timeouts. Polish and English editing instructions can be customized in [`src/ai_prompts.py`](src/ai_prompts.py).

**Activate AI functions** sends a short connection test that may consume tokens. **Improve list captions** sends caption descriptions and grouping metadata to the selected provider. It does not send the DOCX file, images, table contents or source fields. Caption text itself may contain sensitive information, so choose the provider accordingly.

Only one AI request can run at a time. The button stays disabled until the result or an error is returned, preventing repeated clicks from wasting tokens.

### Tests

Run the standard test suite with:

```powershell
uv run --locked python -m unittest discover -s tests -v
```

The tests use generated documents, mocked page maps and mocked AI responses. They do not modify personal files or contact an AI provider. The optional real-Word pagination test can be started separately:

```powershell
$env:RUN_WORD_TESTS = "1"
uv run --locked python -m unittest discover -s tests -p test_word_integration.py -v
Remove-Item Env:RUN_WORD_TESTS
```

## 2. User guide

### Example: from a messy document to a clean result

Imagine that a thesis contains these captions:

```text
Figure 2. Sales results on the left and profit results on the right (shown in grey)
Figure 7. Customer distribution
Figure 5. Forecast accuracy
Table 9. Model comparison
```

The numbering is inconsistent, the first caption describes two images, and unnecessary visual commentary has reached the list. With Full Rework, you can review the objects, choose separate numbering for the first image group, edit the captions and apply one format:

```text
Figure 1–2. Sales results and profit results (Source: own elaboration)
Figure 3. Customer distribution (Source: survey data)
Figure 4. Forecast accuracy (Source: own elaboration)
Table 1. Model comparison (Source: model results)
```

The app can then create a clean list:

```text
List of Figures
Figure 1. Sales results ........................................ 4
Figure 2. Profit results ....................................... 4
Figure 3. Customer distribution ............................... 7
Figure 4. Forecast accuracy .................................... 9
```

AI can suggest shorter entries such as **Sales results** and **Profit results**, remove phrases such as “shown in grey,” and split an explicitly described image group. You still see the original and suggested versions and decide what should remain.

### Full Tables and Figures Rework

1. Upload a `.docx` file. The app scans figures, tables, existing lists and physical page numbers.
2. Select **Full Tables and Figures Rework**.
3. Choose the document language, labels, font, size, text styles, source format, table-caption position and treatment of multiple images.
4. Review detected figures and tables. Exclude logos, decorative icons or other objects that should not be numbered. Exclusion affects the workflow only; it does not delete the object from the document.
5. Review every caption and source. Highlighted rows need attention. Missing captions can be created at the detected object position.
6. Confirm the captions and review the formatted result.
7. Download the captioned document immediately or create new Lists of Figures and Tables.
8. Edit list descriptions manually or activate AI and select **Improve list captions** to receive time-saving suggestions.
9. Review all AI changes, create the final DOCX and download the new file.

### Refresh List of Tables and Figures

1. Upload a document that already contains a recognizable **List of Figures**, **List of Tables**, **Spis rysunków** or **Lista tabel** heading.
2. Select **Refresh List of Tables and Figures**.
3. Confirm the detected language, labels, table-caption position and list style.
4. Review the detection summary. Objects without matching captions are clearly reported.
5. Decide whether grouped images should produce one shared entry or one entry per image.
6. Correct list descriptions manually or use **Improve list captions** for AI suggestions.
7. Confirm the lists and download the refreshed DOCX.

### Benefits and limitations

| Benefits | Limitations |
| --- | --- |
| You can access all tables and figures in one place with previews. | Full processing requires Windows and desktop Microsoft Word. |
| Renumbers captions and produces consistent figure and table lists. | It does not update phrases such as “see Figure 3” in running text or create Word cross-reference fields. |
| Supports Polish and English documents. | Detection focuses on body-paragraph images and body tables; headers, text boxes, nested tables, charts and SmartArt are not fully supported. |
| Keeps the original document unchanged and exports a new copy. | Unusual document layouts or captions far from their objects may require manual review. |
| Provides previews and human approval before changes are saved. | Generated caption paragraphs replace existing inline fields and special formatting with formatted text. |
| Optional AI can shorten descriptions, remove unnecessary commentary and split clearly described groups. | AI reviews caption text, not image pixels, and its wording still requires human judgment. Hosted providers may charge for requests. |
| Validates AI output and blocks duplicate requests to reduce accidental token use. | Refresh uses page positions from the uploaded layout; large changes to list length may make refreshed page numbers outdated. |

Author:
Kamil Maciejko
