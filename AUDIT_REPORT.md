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
