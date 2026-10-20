# Creator Video Studio

Creator-led scriptwriting, reference research and NVIDIA API video review.

Use Python 3.11+, install FFmpeg, then:

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -e ".[studio,riva,test]"
.venv/Scripts/python.exe -m uvicorn studio_server:app --host 127.0.0.1 --port 8765
```

Open http://127.0.0.1:8765/writer. Copy `.env.example` to `.env` and configure your NVIDIA credentials locally.

GPT-OSS drafts with reasoning enabled; NVIDIA independently scores each draft and may request one rewrite. Short, mid and long scripts appear in one editable text area. API calls have a shared 600-second generation deadline. Video uploads use NVIDIA visual review; editorial scores are not calibrated virality probabilities.

The creator reference desk combines book principles, official platform guidance and identified editorial heuristics. Emotion, recognition, shareable observations and resolved story promises guide subtle product integration. References inform prompts; they do not fine-tune model weights. Supply verified product facts and authentic creator experience in the brief.

Optional local tools: `pip install -e ".[local]"`. Saved work, uploads, secrets and model caches are ignored. NVIDIA Riva Whisper setup is documented in [RIVA_SETUP.md](RIVA_SETUP.md). It is prepared for future use and is not automatically invoked by the writer.

Validation: `.venv/Scripts/python.exe -m unittest discover -s tests -p "test_studio*.py"`. Browser checks live in `tests/check_*_browser.py`. Existing license and notices remain in LICENSE.


Video uploads now combine timestamped NVIDIA visual observations, Whisper word timings and a cloud cognitive simulation. An attention estimate below 70 triggers one script rewrite and a three-page `audit.pdf` containing critique, exact-timestamp screenshots and original/revised script excerpts. Rewrites receive an independent text score; unsuccessful rewrites remain marked as needing review. Source-video metrics shown in the writer describe the source video, not the new text.

Audio uses `GROQ_API_KEY` when explicitly configured, otherwise an existing cached Faster Whisper model on CPU. Local transcription runs in a bounded worker and does not download new models. WPM uses full clip duration; ASR speech-free gaps longer than one second may still contain background sound. Missing audio remains explicitly unavailable.

`COGNITIVE_API_KEY` optionally overrides the NVIDIA key. `COGNITIVE_MODEL` selects Nemotron 3.5 Super VL (default) or Nemotron 3 Ultra (`nvidia/nemotron-3-ultra-550b-a55b`), from either the environment or ignored `.env`. Both retain enabled reasoning; bare model names are normalized to the NVIDIA namespace. Live checks on 2026-10-21 returned HTTP 410 for the requested plain Llama 3.1 70B ID and HTTP 404 for 405B, so the operational default is NVIDIA Nemotron 3.5 Super VL. Model identity and evidence limitations are retained. Cognitive estimates are editorial hypotheses, not measured emotion, retention or conversion.

NVIDIA's official `vss-ask-video` skill was installed globally through `npx skills add nvidia/skills --skill vss-ask-video --agent codex --global --yes`. Its deployed-VSS prerequisites differ from this direct-NIM app. No VSS cluster, fine-tuning service or vector database is required by this implementation.

NVIDIA writing retries one transient connection failure or HTTP 500/502/503/504 with a fresh client inside the same ten-minute deadline. Authorization, quota and retired-model failures are not retried. Waiting requests report progress every 15 seconds without exposing private reasoning.

Short/mid GPT-OSS and Nemotron 3.5 drafts and hooks use balanced (`medium`) reasoning to reduce drafting delay. Reasoning remains enabled; long drafts, independent scoring and cognitive analysis keep full (`high`) effort. Set `SCRIPT_DRAFT_REASONING_EFFORT=high` to use full effort for all drafts. No hard thinking-token budget is used. Stage timings are saved with the writer usage diagnostics.
