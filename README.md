# Creator Video Studio

Creator-led scriptwriting, reference research and NVIDIA API video review.

Use Python 3.11+, install FFmpeg, then:

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -e ".[studio,riva,test]"
.venv/Scripts/python.exe -m uvicorn studio_server:app --host 127.0.0.1 --port 8765
```

Open http://127.0.0.1:8765/writer. Copy `.env.example` to `.env` and configure your NVIDIA credentials locally.

GPT-OSS drafts with reasoning enabled; NVIDIA independently scores each draft and may request one rewrite. Short, mid and long scripts appear in one editable text area. API calls have a shared ten-minute generation deadline. Video uploads use NVIDIA visual review; editorial scores are not calibrated virality probabilities.

The creator reference desk combines book principles, official platform guidance and identified editorial heuristics. Emotion, recognition, shareable observations and resolved story promises guide subtle product integration. References inform prompts; they do not fine-tune model weights. Supply verified product facts and authentic creator experience in the brief.

Optional local tools: `pip install -e ".[local]"`. Saved work, uploads, secrets and model caches are ignored. NVIDIA Riva Whisper setup is documented in [RIVA_SETUP.md](RIVA_SETUP.md). It is prepared for future use and is not automatically invoked by the writer.

Validation: `.venv/Scripts/python.exe -m unittest discover -s tests -p "test_studio*.py"`. Browser checks live in `tests/check_*_browser.py`. Existing license and notices remain in LICENSE.
