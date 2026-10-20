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


Latest API review migration: new uploads call NVIDIA directly, bypass local model
execution and GPU admission checks. MP4 limit is 20 MB. Automated suite: 301 tests
passed. Writer and optional review browser regressions passed; main remote
report dashboard passed desktop/mobile checks with no JavaScript errors.
Live upload reached NVIDIA but the first invocation returned a connection error;
the retry completed successfully in 171.3 seconds with hook 55, pacing 70 and overall 40, plus timestamped advice. No scores or verdict were assigned on the failed invocation.


Product persuasion audit (20 October 2026): full suite 305 tests passed; all four
browser workflow checks passed; ten health/configuration/read endpoints returned
HTTP 200. Live NVIDIA hair-catcher scripts took 69.7 seconds initially, 20.3
seconds on retest, and 24.6 seconds for the requested revision. Final output was
65 words, estimated 24-32 seconds, and appeared in the real writer UI with no JS
errors. Real draft-save and export matched exactly.

Fixed fail-fast connection handling with one fresh-client retry inside the total
180-second deadline (no HTTP/timeout retries). Added grounded persona directions
and selected book principles to the compact prompt. Found and blocked invented
first-person product routines and unsupported dry-fingers/no-touch promises.
A four-page PDF with exact generated script and test limitations is saved locally
under results/audits/2026-10-20/. No conversion or virality probability was claimed.


Multi-format direct-response pipeline: added content_duration short/mid/long with
35-60, 140-170 and 1,500-1,800 spoken-word gates. New outputs use a single
final_script string. Mid cues and Long section markers remain inline. The API
pre-scoring gate validates five exact fields and allows at most two drafts in
one run (initial plus one rewrite); missing CTA, invented experience, score below
80, or deterministic constraint failures prevent approval. Scoring/rewrite
outages retain diagnostics and saved work without approval. Rejected output is
hidden from the publishable textarea and cannot be exported.

Validation: 319 tests passed; writer and multi-format browser workflows passed
with no JavaScript errors or mobile overflow. The live Short test produced 46
words and a 95/100 gate assessment in 43.1 seconds. Live Mid produced 154 words
but the judge miscounted it; scoring now receives the authoritative code-counted
word total. A subsequent score took 5.8 seconds and rejected it for repetition.
Long produced in-range drafts (1,564 and 1,759 words), with unsupported experience
or claims correctly blocking approval. An independent fast score rejected the
1,564-word draft at 75 in 10.5 seconds. These do not prove sales or virality.

Provider findings: native json_schema requests returned HTTP 500 in a minimal
hosted endpoint check; json_object succeeded and is now used with strict app-side
schema validation. Some live runs encountered HTTP 500 and output-budget
exhaustion. Short/Mid Nemotron drafts use low reasoning and 8,192 tokens; long
output uses 12,000 tokens with thinking disabled. Scoring also disables thinking.
Each team/fast request retains its 180-second total bound and one fresh-client
connection retry. The entire multi-stage run can exceed 180 seconds. No automatic
HTTP retries, extra voice-edit rewrites, or fabricated approvals were introduced.
