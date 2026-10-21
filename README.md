# Creator Video Studio

Creator-led scriptwriting, reference research and NVIDIA audio-visual video review.

Use Python 3.11+, install FFmpeg, then:

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -e ".[studio,riva,test]"
.venv/Scripts/python.exe -m uvicorn studio_server:app --host 127.0.0.1 --port 8765
```

Open http://127.0.0.1:8765/writer. Copy `.env.example` to `.env` and configure server-side credentials locally. Never commit keys or private uploads.

The multi-format writer makes three logical calls: draft, mechanical self-critique, and editor. The editor returns one shared script body with three selectable openings: problem, curiosity and contrarian. Short, mid and long scripts appear in one editable, automatically expanding text area. Switching openings preserves the body and inline cues. All three variants must pass deterministic safety and format checks before export; no fabricated model score is displayed. Failed stages retain completed drafts for review.

Reasoning remains enabled. Short/mid writing stages use medium effort by default; long scripts and cognitive simulation retain high effort. Set `SCRIPT_DRAFT_REASONING_EFFORT=high` to increase draft effort. GPT-OSS, Nemotron and Llama calls stream through the shared transport with progress heartbeats every 15 seconds. Each API call has a 180-second deadline, including one fresh-client retry for a transient connection failure or HTTP 500/502. Total pipeline time can exceed 180 seconds. NVIDIA availability and reasoning latency still affect completion time.

The creator reference desk combines book principles, platform guidance and identified editorial heuristics. A cached sparse-vector lookup selects at most two relevant personas from [SCRIPT_PERSONAS.md](SCRIPT_PERSONAS.md). References guide prompts; they do not train model weights. Provide verified product facts and authentic creator experience. Hooks must be single sentences under 12 spoken words; short hooks cannot ask questions. Scripts retain at least three physical B-roll cues and visual pacing cues every two to three sentences. Instructions prohibit invented routines, unsupported results, anti-selling and robotic CTAs.

Video review extracts sampled frames and mono 16-bit audio concurrently. Whisper supplies transcript, word timings, WPM and speech-free gaps longer than one second. Nemotron 3.5 VL receives actual JPEG pixels plus this speech evidence in one unified cognitive review. The dashboard displays attention estimate, arousal state and WPM. Estimates are editorial simulations, not measured emotion, retention or conversion.

An attention score below 70 triggers a three-stage revision and an automatic PDF audit capped at three pages. The PDF contains critique, exact-timestamp FFmpeg screenshots and a side-by-side transcript/revision comparison. Revisions that fail checks remain flagged. Source-video metrics describe the uploaded clip, not the revised script.

Audio uses `GROQ_API_KEY` when configured, otherwise an existing cached Faster Whisper model on CPU. Transcription does not download new models automatically. Missing audio is reported explicitly. Optional NVIDIA Riva Whisper setup is documented in [RIVA_SETUP.md](RIVA_SETUP.md); it is prepared separately and is not automatically invoked by the writer. `COGNITIVE_API_KEY` optionally overrides the NVIDIA key. Raw-frame reviews use Nemotron 3.5 VL; the Ultra override is retained only for legacy text-observation callers.

NVIDIA skills were installed with `npx skills add nvidia/skills --skill <name> --agent codex --yes` for `nemotron-customize`, `rag-blueprint` and `accelerated-computing-cudf`. Their guidance informs integration choices; the app does not deploy NVIDIA's training stack or full RAG Blueprint. This small workload does not require cuDF. See [ARCHITECTURE.md](ARCHITECTURE.md) for contracts and limitations.

Optional local tools: `pip install -e ".[local]"`. No new local reasoning models are required. Saved work, uploads, secrets and model caches are ignored. Existing license and notices remain in LICENSE.

Validation:

```powershell
.venv/Scripts/python.exe -m unittest discover -s tests
```

Browser checks live in `tests/check_*_browser.py` and require the server on port 8765.
