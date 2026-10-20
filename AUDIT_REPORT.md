# Application audit - 21 October 2026

[Read the full PDF report, including a live generated script](docs/reports/creator-studio-audit-2026-10-21.pdf). The [sanitized evidence manifest](docs/reports/creator-studio-audit-2026-10-21.json) and [PDF generator](tools/build_app_audit.py) are included for reproduction. Runtime source revision: `60b2170`.

## Findings and fixes

NVIDIA returned HTTP 500 for the failing Nemotron non-streaming request; streaming the same diagnostic brief produced JSON. GPT-OSS also answered. The failure was not evidence that both endpoints had disappeared. The request also mixed a facewash topic with shampoo facts, which now fails validation before spending an API call.

The shared transport now streams GPT-OSS and Nemotron 3.5 answers, sends progress heartbeats and makes at most one fresh-client retry for transient failures within the existing 600-second request deadline. Reasoning remains enabled and private. GPT-OSS and Nemotron 3.5 short/mid drafts use medium effort; long scripts, scoring, cognitive simulation and the separate Ultra writer keep high effort. The separate Ultra writer retains its existing streaming client. Set `SCRIPT_DRAFT_REASONING_EFFORT=high` to restore full effort for small drafts.

Compact prompts retain the selected hook, persona, language, creator format, verified facts and research. Locally invalid drafts skip unnecessary remote grading. Unsupported guarantees and product-use mistakes are blocked before approval. Rejected drafts remain editable and can be revised, but cannot be exported as approved. Other fixes cover retry engine selection, cloud reference saving, corrected transcript reuse, retained audio evidence and busy-slot cleanup after worker startup failure.

## Measured output

The live unpleasant-product test used a reusable shower-drain hair catcher. Nemotron produced the first draft in **18.7 seconds** and a reviewed, rewritten **37-word script in 73.0 seconds**, approved by the independent gate at **88/100**. The exact script, product facts and editorial assessment are in the PDF.

A separate GPT-OSS run answered in **76.7 seconds**, but its unsupported every-strand promise kept it unapproved. Hindi Nemotron output passed at **88/100 in 186.6 seconds**; human review found the voice grammatical but plain. These are observations under variable provider load, not controlled speed comparisons or proof of sales or virality.

## Verification

- **344 unit tests passed** in 10.669 seconds.
- **Six browser workflows passed**: writer, multi-format, cognitive evidence, optional video review, brand and saved review. Zero JavaScript errors; no mobile overflow.
- Installed dependency consistency, Python parsing, JavaScript syntax and whitespace checks passed.
- Final-code server restarted and returned a healthy NVIDIA configuration at `http://127.0.0.1:8765`.
- Live cloud video/audio evidence and failure handling are documented separately from mocked browser/unit checks in the PDF.

The suite covers the app workflows and known failure paths; it cannot certify every product, language, model response or future provider outage. Editorial scores remain uncalibrated, and longer formats and representative customer videos need further audience testing. Raw user jobs, credentials, uploads and local benchmark logs are excluded from the published report.

Rebuild the PDF with:

```powershell
.venv\Scripts\python.exe tools\build_app_audit.py docs\reports\creator-studio-audit-2026-10-21.json --output docs\reports\creator-studio-audit-2026-10-21.pdf
```
