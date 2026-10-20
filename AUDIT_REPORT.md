# Audit report — 20 October 2026

The full repository suite passes: **290 tests**. No broken installed package requirements were reported. Studio Python syntax checks and all four JavaScript syntax checks pass.

## Fixes

- Restored Hindi sentence punctuation and curly apostrophe handling in the single-block script validator; full-width opening questions are rejected consistently.
- Clear previous Gemma scores before retrying, including when the retry returns an HTTP error. Ignore outdated responses from earlier dashboard renders.
- Bind Gemma results to the uploaded MP4's SHA-256. Replaced, missing, changed-during-review or invalid recordings cannot reuse old scores.
- Reject corrupted Gemma score metadata without assigning an approval verdict.
- Isolate damaged saved-script metadata so one bad file does not break the saved-work list.
- Close rejected reference-video uploads.
- Render archived evidence records that predate explicit source-kind metadata in decision PDFs.
- Replace an obsolete PDF browser assertion that assumed every detailed report had three or four pages. The saved report checked has eleven pages, fourteen embedded images and no link annotations.

## Verification

- `python -m unittest discover -s tests`: 290 passed.
- `python tests/check_writer_browser.py`: single text area, copy/save/export, revisions, archived drafts, desktop/mobile passed.
- `python tests/check_gemma_browser.py`: background polling, scores, HTTP retry failures, desktop/mobile passed.
- `python tests/check_studio_browser.py`: saved video review, PDF text/images and desktop/mobile passed.
- `python tests/check_brand_browser.py`: brand documents, references, feedback, PDF and desktop/mobile passed.
- `python -m pip check`: no broken requirements.
- All browser checks reported zero JavaScript errors and no mobile overflow.

Automated inference tests use controlled responses; they do not prove model accuracy or provider uptime. The earlier live GPT-OSS single-block request completed in 34.6 seconds. The latest live Gemma MP4 request failed after 152.4 seconds without scores. Gemma availability therefore remains unverified; the app reports that failure without inventing a score. No local GPU stress run or additional paid inference was needed for these changes.


## Provider failure diagnosis and working replacement

Live diagnostics reproduced NVIDIA HTTP 504 with `nvcf-status: errored` for a tiny Gemma 4 text request. Polling that errored request returned 404; it was not a recoverable queued invocation. Streaming and an explicit 180-second gateway hold also failed to return Gemma output. The model-list endpoint was healthy and an alternative vision model worked with the same credential.

API Video Review now defaults to `nvidia/nemotron-3.5-super-vl-120b-a12b`, with Gemma 4 retained as an explicit manual-retry choice. A direct MP4 test completed successfully, and the complete app flow then processed the saved 33.8-second MP4 in 25.1 seconds. The main server's saved result and browser dashboard both identify Nemotron accurately. Scores are uncalibrated visual editing estimates; the model explicitly noted that audio was unavailable.

The client sets NVIDIA's gateway hold window to 180 seconds, polls valid HTTP 202 request IDs without resubmission, reports provider 504/errored status distinctly from a client timeout, and discards tagged private reasoning before parsing JSON. Four regression tests cover the gateway error, request-ID validation, reasoning exclusion, and accepted-request polling. The full suite now passes 294 tests; writer, video-review and live saved-result browser checks pass.
