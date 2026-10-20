# Creator Video Studio guide

## Start and configure

Install the dependencies in [README.md](README.md), then use **Start Studio.cmd** or run Uvicorn. Open http://127.0.0.1:8765. The launcher uses the project virtual environment. Keep keys in ignored `.env`; never paste them into the browser or commit them.

## Write a creator-led script

Open **Script Writer**. Supply a product/topic, verified facts, audience, niche, language and authentic creator context if available. Saved brand documents supply factual context. Select a persona, content format and duration:

- Short: 35?60 words, an immediate hook and one purchase action.
- Mid: 140?170 words with pacing cues every three sentences.
- Long: 1,500?1,800 words with 3?5 sections and one action near the end.

GPT-OSS is the default writer when its credentials are configured. NVIDIA independently scores the draft. Reasoning stays enabled, with up to 180 seconds per generation request and one fresh-client retry for transient connection failures inside that deadline. Failed jobs retain completed drafts. The scoring gate allows one rewrite; rejected output is not presented as approved.

Scripts appear in one expanding text area. Copy, edit, save or export the text. **Suggest changes** creates a new revision using your edited draft and instructions, preserving the original. Manual edits invalidate the displayed approval until reviewed again.

The creator reference desk prioritizes emotional recognition, watchable progression, shareable observations, honest curiosity payoffs and relevant product integration. Principles and applications are passed into generation, and the selected cards appear under **References applied**. Official platform guidance, book summaries and original editorial heuristics are identified separately. References guide inference; they do not fine-tune weights or establish a guarantee of virality. Product claims must come from supplied facts; no fabricated personal routines or results.

Local writing is available with optional local dependencies and downloaded models. Hugging Face writing requires explicit credit-use opt-in. Hosted engines send brief/reference context to the selected provider and are subject to account limits.

## Review a video

Upload an MP4 up to 20 MB through **Video review**. NVIDIA Nemotron analyzes visual evidence and returns hook, pacing and overall editing estimates with timestamped advice. Jobs run in the background and report failures explicitly. Scores are uncalibrated editorial estimates, not measured probabilities of virality or sales. The visual endpoint may not hear audio; consult the evidence and limitations shown in the report.

Previously saved reports can be reopened and exported. The separate **AI video review** card on saved reports supports NVIDIA Nemotron and optional Gemma. Model outages do not produce invented scores.

## Research and experiments

The Muse panel researches accessible reference videos, prioritizing YouTube Shorts, then TikTok, then Instagram. Existing local Whisper research transcribes actual speech. Muse examines timestamped evidence and reference principles to propose conditional mechanisms. Matching niche/language notes can guide future writing. Private or inaccessible sources are skipped. Observed views do not establish why a clip succeeded.

Record your own experiments with dates, variants, exposure, audience and outcomes. Kumo's optional estimate requires comparable real account history; it remains distinct from the editorial score.

## Prepared Whisper module

NVIDIA Riva Whisper Large V3 is installed for future explicit use. It is not connected to automatic research or writing. See [RIVA_SETUP.md](RIVA_SETUP.md).

## Saved data and diagnostics

Ignored `results/` contains uploads, scripts, research and reports. Ignored `cache/` contains optional model files and SDK examples. `.env` holds local credentials. Keep these when updating source code. Run the Studio unit tests and browser checks described in README.md when changing workflows.

The audio/cognitive audit pipeline and model configuration are described in README.md. Attention estimates below 70 trigger one rewrite and an audit PDF with a hard three-page limit.
