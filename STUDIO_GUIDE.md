> Current GPU policy (2026-10-20): automatic maximum with 512 MiB desktop reserve and 256 MiB additional worker margin. On the tested 6 GiB GTX 1660 Ti, the target is 5.5 GiB. Historical 4 GiB measurements below describe the previous configuration. The 82 C stop and temperature-aware pacing remain active. Hosted Muse/Nemotron inference uses NVIDIA servers, not this GPU.

# Local creative report studio

## Script Writer

Open **Script Writer** from the Studio home page, or visit <http://127.0.0.1:8765/writer> after starting Studio. Enter a product/topic and verified facts, audience, platform, language, duration, writer persona and optional ending/CTA. Select a saved brand to include a bounded excerpt of its guidelines/product brief. Optionally paste a completed analysis job ID to incorporate its creative-review summary. These excerpts are context, not a replacement for checking the full brand documents.

The recommended local writer is **Qwen3.5-4B Q4_K_M**, downloaded once with `.venv\Scripts\python.exe prepare_writer.py`. The roughly 2.74 GB model file is pinned to a repository revision and SHA-256 checksum before activation. It runs entirely on this PC and does not use HF inference credits or need a token after download. **Recommended installed model** selects it when present; **Qwen3 4B compatibility model** remains selectable. Video review keeps its existing model. The local writer keeps full GPU offload, the 4 GB resource budget and temperature pacing; no larger model is forced into RAM or used through an unannounced CPU fallback. Omitted reference metadata is kept as an empty list rather than discarding valid spoken copy or inventing citations. Empty improvement notes for strong grades use an explicit no-specific-change placeholder; weak grades still require a real improvement. Model identity participates in completion-cache signatures, and reasoning is disabled for Qwen3.5 script generation. Its more conservative thermal profile pauses at 73 C until 70 C, uses smaller token bursts and spaces requests by 350 ms to reduce spikes; the existing active-inference stop remains unchanged.

Stopped hosted jobs offer **Retry locally (free)**. This explicitly changes the saved request to local, disables HF credit usage and retains the brief, brand context, seed, drafts and old checkpoints. Opening a failed hosted job also resets the form to Local so generating another draft does not repeat the credit failure.

**Writing engine** defaults to **Local**, with no hosted inference charges. The optional **Hugging Face** engine offers DeepSeek V4.1 Flash, DeepSeek V3.2 and Qwen3 235B Instruct through the HF router using only your Hugging Face token. Model availability changes; these were present in HF's router catalog when added. Hosted writing runs the same persona, reference-library, revision, word-budget and deterministic claim checks on a remote model, without loading the local GPU model or waiting for GPU cooling. No claim of improved creative quality has been benchmarked yet.

Hosted inference is not unlimited free. HF offers limited included credits and may use paid account balance after that. Local remains active and the credit checkbox is off by default. The API also refuses hosted jobs without explicit credit-use opt-in. The software does not purchase credits, change billing settings, silently change your selected model or switch a local job to hosted inference. The underlying HF provider can vary with its cheapest routing policy. See [HF pricing](https://huggingface.co/docs/inference-providers/pricing).

Use an existing `HF_TOKEN` in the server environment or ignored project `.env`, or the token saved by `hf auth login`. The token must have **Make calls to Inference Providers** permission. The page shows only whether a server token is configured; it never receives or saves the token. Hosted requests send the brief, selected reference context and drafts to HF and its selected inference provider. No separate provider key is needed. [HF setup](https://huggingface.co/docs/inference-providers/index).

Hosted jobs retain completion checkpoints separately from local inference. Retry restores matching completions; model, system, library or writer-version changes invalidate incompatible output. Each run permits at most 24 new completion requests with capped output tokens, with no automatic transport, rate-limit or credit-exhaustion retries. Semantic/JSON repair still uses bounded model calls. Failed jobs retain already validated drafts. `hf_writer_usage.json` records reported token usage and call counts, not a dollar estimate or proof of free usage. Hosted routing uses HF's `:cheapest` policy for the selected model. The existing shared job slot still prevents overlapping work.

Choose **Organic social** (default), **UGC / creator content**, or **Paid ad**. Organic and UGC prioritize a watchable story, useful observation or entertaining moment with natural product presence. They do not require an ingredient list, brand-led opening, sales end card or shopping CTA. Leave the ending/CTA field blank for a story resolution, callback or natural question. Their review rubric rewards a suitable ending even with no request; revisions should not turn the piece into an ad to raise the score. Paid ad retains product/benefit communication and CTA guidance.

Choose a format such as POV/sketch, storytime, day-in-the-life, useful tip/how-to, comment reply or first look/unboxing. Add the creator's actual setting, observations and experience in **Creator context / real experience**. UGC uses conversational language and everyday observations. It must not invent purchases, weeks of usage, endorsements or results. Without experience notes it can use a first look, factual observation or clearly staged sketch.

Generate five hook options and pick one, or write a script directly. Each script contains only words to say aloud. The local writer receives original reference cards covering *Made to Stick*, *Contagious*, *Everybody Writes*, *Building a StoryBrand*, published research, and Google/TikTok/YouTube guidance. The library links to primary sources and distinguishes research, platform advice and Studio editorial heuristics. Full books are not bundled, downloaded or used to train model weights. Edit `script_library.json` to maintain these attributed cards; restart Studio after changes.

After a script is made, use **Suggest changes** to ask for a rewrite in plain language. Select the whole script or one paragraph, then **Apply changes**. Current manual edits are saved and included. The current duration, language, persona and engine settings from the brief apply; use those controls to change them. Each request creates a separate saved job linked to its original; **Open original script** restores the source version without overwriting it.

Local generation publishes a live, read-only preview of spoken text as JSON speech fields arrive. The preview is explicitly unreviewed and has no inherited score; the original stays visible during revision. Validated draft snapshots appear before editorial review finishes. Hosted engines show the preview when their full draft arrives. Final review checks both the normal facts/timing criteria and whether requested changes were applied. Missing or negative edit-adherence review prevents a passing target, even if the copy otherwise scores highly. Revisions keep their requested changes across optimization rounds. Failed changes retain completed drafts or expose the untouched source as unscored if no new draft was produced. Local GPU cooling can still pause updates; real-time preview does not mean instant generation.

**Writer persona** replaces the tone selector with 24 choices, including automatic selection. See [all personas and category fits](SCRIPT_PERSONAS.md). The voices span layered mystery, poetic wit, fourth-wall comedy, relatable rants, fashion opinions, skincare routines, FMCG shopping dilemmas, food commentary and arcade stories. They use original language rather than named-author or character imitation.

Output is **spoken script only**. The editor, clipboard and text/print exports contain no shot directions, subtitles, overlays or staging. Timing and paragraph numbering remain internal for word budgets and critique; saved older drafts remain readable. A solo monologue is the default. Three paragraphs read together as one continuous script with a hook, development and earned payoff.

The reference library contains 22 attributed cards, including ten additions for Instagram guidance, solo filming, rants, routine commentary, beauty storytimes, creator replies and short lists. Meta source cards cover its creator education hub and Trial Reels experimentation guidance. Studio format patterns are labeled editorial heuristics, not evidence of guaranteed reach. At most six relevant cards enter a draft's compact context.

Create the attention trigger in the opening words. English hooks allow up to 18 spoken words. Simple delivery can earn the highest hook grade; elaborate staging is not required. The full spoken script validates its duration and approximate English speaking budget.

New generations use a fresh saved random seed and expressive sampling for hooks and scripts. Review stays deterministic. Retry uses the saved seed and compatible checkpoints. This adds variety without a separate brainstorming model call. It does not guarantee originality or audience attention; check the ideas for suitability and resemblance to existing campaigns.

English duration checks now require at least two words per requested second for an assessed script to pass (60 words for 30 seconds), with a target of 2.4 words/second and an upper budget of three. Paragraphs cannot hide missing copy behind padded timestamps. The editor shows a live word count and estimated read-time range at 120-160 words/minute; actual delivery must be timed aloud. Other languages need a fluent timing check. The upper and lower budgets are editorial checks, not measured audio.

Deterministic blockers cap the score below 80 for missing duration, unsupported personal reactions such as dryness, invented biological feeding explanations and misleading rinse implications. These checks apply to saved scored drafts on read as well as new reviews; a model's praise cannot override them. Unsafe selected hooks are treated as ideas to rewrite, not as verified facts. Quality blockers enter the next revision prompt, rather than merely being displayed after generation.

The 18-word limit applies only to hook options, not every script paragraph. Paragraphs use their allotted speaking time, with explicit numeric word budgets and targeted shortening of overlong paragraphs. Original wording is never silently truncated. Unsupported shampoo-use instructions receive a targeted paragraph repair without regenerating valid paragraphs. Negated warnings such as "not a leave-in" are not mistaken for leave-in instructions. Unsupported directions are never approved to force completion; if repair still fails, the writer retains its safety error.

Overlong English hooks are saved and flagged as editorial issues, rather than rejected as malformed JSON. Generation aims for 6-12 words and repairs only flagged options to the 18-word limit. If the limit remains unmet or a rewrite cannot be validated, the original wording remains visible with a needs-review warning; it is never silently chopped or labeled reviewed. Retry saved jobs to use updated writer validation.

The hook generator also critiques its five options for logical contradictions, unsupported capabilities, invented testimonials and missing payoffs. It allows one rewrite of flagged options, preserving the other hooks. Draft hooks are saved and displayed before the critique finishes. Unresolved issues are shown beside their hooks; malformed reviews leave the hooks available with an explicit **review unavailable** warning. Neither state is presented as a successful review. Long review explanations are shortened for display instead of failing the job. These checks use the same local model and still need human review. Product slogans must not become usage directions; checks flag unapproved no-rinse shampoo directions, application timings and invented beneath-the-skin claims.

The writer critiques and revises scripts toward **80/100 script editorial readiness**, using six criteria: hook (20%), clarity (20%), structure (15%), credibility (20%), relevance (15%) and CTA (10%). Integer grades from 0–4 produce the score in application code. Critiques must cite real internal paragraph numbers. Reported unsupported claims or missing proof prevent a passing result. English word budgets reject clearly overfilled timelines; other languages need a fluent speaker's timing check. Even an English word budget is only a rough feasibility check, not measured delivery time.

This is an uncalibrated local text-model critique. It does **not** run TRIBE v2 fMRI inference, grade real voice/visual execution or predict views. Revision stops on a score of at least 80, an unchanged draft, two rounds without a better score, or five total assessed rounds. Invalid structured responses receive one repair attempt. Each validated draft is saved before critique; a stopped review leaves it available as **Unscored**, without claiming the target was reached. The best scored draft and each assessed round are retained. A resource guard, timeout or model failure can stop a job earlier while retaining completed work; no score is fabricated to meet the target. A separate critique prompt uses the same local model, not an independent human or independently trained evaluator.

Edit the scene fields, save changes, regenerate a selected scene or refine the whole edited draft. Manual edits invalidate the displayed score until a new generated revision is assessed. Text export and **Print / PDF** use the saved edited draft when one exists. Print / PDF opens a print-friendly page; use the browser's Save as PDF destination. Upload the finished video through Video review to assess actual recorded execution.

The experiment notebook stores your own hypotheses and observations. Record dates, variant wording, exposure, audience, retention and conversions; the writer can include your two latest notes. These are unverified observations, not causal evidence or automatic platform experiments. Reference cards and experiment notes stay local. Script jobs share the same exclusive GPU slot, model, 4 GB target, temperature/memory guards and 30-minute worker limit as video reviews. Long or dense briefs may exceed the 6,144-token model context; shorten them if requested. Work is saved under `results/studio/_scripts/`. Reopening the writer restores the latest selected job in that browser. **Retry saved job** resumes stopped jobs or regenerates flagged hooks using their saved inputs and compatible completion checkpoints. Completed drafts remain available. A brief network interruption retries polling automatically.

Writer inference uses compact, task-relevant library cards and removes brand text already present in the supplied facts; distinct brand rules are retained. Critiques request short explanations, and revisions carry forward changes rather than repeating whole critiques. If a critique has one invalid criterion, only that criterion is regenerated while valid grades are retained. Scene regeneration requests only the selected scene and preserves its neighbors and timings in code. Writer HTTP work units are larger than video-review units (192/48 prompt/output tokens below 68 C, 128/32 below 72 C, 64/16 above that), reducing request overhead while retaining checks between units. Model batch sizes, the 4 GB budget, 75/72 C cooling thresholds and emergency guards remain unchanged. A new job waits for a warm GPU to cool rather than immediately failing at startup. Timing depends on the brief, revisions, other applications and cooling; the UI shows elapsed time. `review_profile.json` and `telemetry_review.json` retain request counts, inference/cooling times and sampled GPU usage for comparison.

Verification: `python -m unittest tests.test_studio_script_writer` covers score calculation, proof blockers, scene validation, revision stopping and API persistence. With Studio running, `python tests/check_writer_browser.py` checks the browser flow with generation mocked, without starting GPU work.

Double-click **Start Studio.cmd** in the folder you cloned or downloaded. It starts the local server and opens <http://127.0.0.1:8765>. Keep using that address; opening `web/index.html` directly cannot run analysis. Double-click **Stop Studio.cmd** to stop this project's server and its active model workers. Saved reports are kept. Reopen an interrupted job and use **Resume saved analysis**; completed review sections are reused. In-progress token output is also checkpointed after each burst and resumed only when its model/input/prompt signature matches. New machines should first follow [TEAM_SETUP.md](TEAM_SETUP.md).

From the VS Code terminal (PowerShell), in the repository root:

```powershell
.\.venv\Scripts\python.exe studio_server.py
```

Leave the terminal open, visit <http://127.0.0.1:8765>, and press **Ctrl+C** in that terminal to stop an idle server. For an active job use **Stop Studio.cmd**. Opening the server does not start model inference.

### Fast GPU processing with temperature-aware pacing

Speech, sampled-frame descriptions and text review use sequential GPU workers, without automatic CPU fallback. RapidOCR runs deliberately on CPU/ONNX between these stages to preserve GPU headroom. File handling, decoding, tokenization and PDF export also use CPU/system RAM. The earlier review runtime logged a CUDA illegal-memory-access crash; the new review configuration uses full layer offload, smaller requests and plain f16 cache with Flash Attention disabled. A short guarded runtime check cannot guarantee that every future video or driver state will be stable.

The GPU target is fixed at **4 GB total usage**, including other applications. The watchdog stops the current model at **3.75 GB**, leaving about 2 GB or more on this 6 GB GPU for the desktop and brief spikes. Review inference pauses between work units at **75 C** and resumes at **72 C or lower**; active inference stops at **82 C**; a reviewer already in a fresh cooling wait may briefly continue at 82-83 C, with an emergency stop at 84 C. Cooling waits are limited to two minutes. These are conservative application settings, not manufacturer temperature specifications or hard system-wide limits.

Jobs and model stages require **1.5 GB available RAM**; running model workers stop below **768 MB**. A safety stop fails the job and terminates its worker tree instead of retrying on CPU. Completed stages are reused when the job resumes. No system-wide GPU power or clock settings are changed. Sampled guards cannot prevent every instantaneous allocation spike or driver crash.

Execution order:

1. Measure the video and audio.
2. Transcribe speech using 15-second windows, one worker, with pauses between returned segments.
3. Terminate the speech worker to release CTranslate2 allocations. Run local RapidOCR at 0.8 fps, with bounded extra probes around the largest measured visual changes and the final frame. Near-duplicate overlays are deduplicated. Keep the timestamped original text and frame crops without translation. Describe diverse sampled frames even when OCR is plentiful, and measure audio variation from the actual decoded waveform.
4. Terminate the caption worker. Give the text reviewer speech, OCR, audio measurements and secondary sampled-frame descriptions, then generate a concise narrative and strengths. The text model does not receive pixels directly; uncertain captions must not override a legible product label or CTA. Audio variation is not a direct measure of emotion.
5. Rate all eight criteria in a bounded batch; regenerate only unsupported individual ratings.
6. Generate each exact edit in a separate request, covering every weak criterion.
7. Unload the review model, then decode, resize and encode clips using NVIDIA NVDEC, CUDA scaling and NVENC H.264. Clips are rendered sequentially with GPU memory/temperature monitoring. Audio encoding, small measurements, file I/O and PDF layout still use the CPU; those operations cannot all be transferred to CUDA.

The reviewer uses a 6,144-token GPU context with compact source metadata, preserving the original speech and OCR for ordinary short ads without summary calls. Longer evidence is condensed with exact CTA/label excerpts retained. Review bursts adapt to temperature: prompt/output limits are 96/32 tokens below 68 C, 48/16 below 72 C, and 24/8 above that until cooling begins. Shared evidence stays cached in the current GPU slot. There is no fixed delay when below the pause threshold. At 75 C the reviewer waits until the GPU cools to 72 C; warm bursts stay small to leave headroom. The 82 C stop guard stays enabled. This replaces the old three-second pause on every request. Throughput depends on cooling and competing applications; no fixed completion time is promised. The review model and its current GPU context stay loaded between bursts but is not generating during those pauses. Completed sections are checkpointed with an input signature. After a failed run, click **Resume saved analysis** to reuse the saved upload, transcript, frame evidence and valid completed review sections. Input or prompt changes invalidate the corresponding checkpoints. The model retries only a failed section rather than regenerating every valid section. Exceptionally dense transcripts are summarized in bounded sections, so compressed evidence can lose nuance. The original transcript remains available in the report.

1. Drop a video into the upload box.
2. Leave **4 GB** selected. This is the fixed conservative target on your 6 GB GTX 1660 Ti; the previous 4.5/5 GB choices are disabled.
3. Choose the speech language (or Auto), platform and optional audience. Keep visual descriptions enabled for additional sampled-frame evidence.
4. Click **Analyze video**. After completion, read the detailed review and exact edit plan, play or download the clips, and use **Download PDF**.

Videos stay on this computer. The first use may download model weights from Hugging Face; the video is not sent to an external inference service. One video is processed at a time. Uploads are limited to 250 MiB, 10 minutes, and at most 4K pixel count. Reports and source uploads are saved under `results/studio/<job-id>/`.

## Detailed multilingual review

Choose Auto detect for supported mixed speech, or set the main language manually: Hindi, Tamil, Telugu, Bengali, Marathi, Gujarati, Kannada, Malayalam, Punjabi, Urdu, Assamese, Nepali, Sanskrit, Sindhi, or English. The selector reflects Whisper's language IDs, not a claim of equal accuracy. Odia and unlisted regional languages/dialects do not have an explicit profile in this model. Always have a fluent speaker check the original-language transcript and replacement wording.

Select a platform and optionally describe the audience and objective. The review explains its reasoning in English, while suggested spoken lines/overlays use the transcript's language and include an English gloss. Automatic detection can still miss short code switches, names and dialect words. Use the manual language override and re-analyze when detection is wrong.

The overall creative score comes from a local semantic review. Eight fixed criteria are graded 0-4: hook (15%); script/message (15%); structure/pacing (10%); credibility (10%); emotional relevance (5%); CTA (10%); voice/delivery (15%); visual presentation (20%). Their instructions now ask about attention triggers, comprehension load, trust gaps and action friction where the actual evidence supports them. Every judgment cites supplied speech, OCR, audio or sampled-frame evidence. The app validates source IDs and grades and computes the total independently. Readable captions alone do not establish visual quality, and a catchy slogan is not an actionable CTA.

The **virality checker** appears beside the overall rating in Studio and the PDF. It is a separate 0-100 creative-spread readiness index using the existing evidence-adjusted grades: stop the scroll (25%), hold attention (25%), deliver a payoff (20%), reason to share (15%), and prompt a response (15%). Each lever shows its score, cited evidence, main constraint, and any matching timestamped edit. The index excludes brand compliance and adds no model inference time. It is not a probability of going viral, a view forecast, or a measured retention/share rate. Compare it with actual platform results before trusting it as a predictor.

The report also maps likely viewer-response bottlenecks: attention, comprehension, trust and action motivation. Each map entry names the weakest relevant creative criterion and cites its source IDs. This is an editing hypothesis derived from the eight grades; it does not double-count points, measure brain activity, or predict actual audience behavior. Checking these hypotheses against retention and conversion data requires labeled outcomes.

The webpage includes playable, downloadable excerpts. PDFs embed actual video screenshots at edit ranges and for opening/middle/closing previews, so images remain visible when shared or opened offline; PDFs do not contain clip links. Both include the summary, strengths, category rationale, original transcript, and exact edits. Each edit names its original timestamp range, cut/replace/move/overlay instruction, replacement wording, reason, and acceptance check. Timestamps refer to source transcript segments; after cuts, the final timeline will differ. Screenshots show the original footage, not the suggested future edit.

For videos rated below 70, a dedicated priority list links every criterion below 3/4 to concrete timestamped edits. Both the webpage and PDF include this list. The summary covers the topic, audience, progression, best moments, weaknesses and available criteria, with detail proportional to the source evidence.

**75/100 is an editing target, not a predicted post-edit score.** A grade of 3 in all eight categories totals 75. Apply the concrete edit plan and upload the edited video to assess it again. These scores remain uncalibrated AI editorial judgments; a more detailed model does not validate virality forecasts. Actual views, retention, shares and conversions require platform data. Sampled frame captions can misidentify products and are not equivalent to watching every frame. Audio level and pitch measurements can be distorted by music or noise and cannot determine authentic tone on their own.

The old small speech model and English keyword composite are no longer used for new reports. If semantic analysis fails, no replacement keyword score is assigned. Underlying measurements and validated review are saved in `report.json`; model worker logs stay local.

The detailed PDF uses Microsoft Edge's font shaping to preserve Indian scripts. Microsoft Edge and the Python Playwright package must be installed. Detailed review runs on GPU in sequential parts and can take several minutes; long multilingual clips may take longer. A stage times out after 30 minutes. Dense transcripts are read in sections rather than silently truncated; exceptionally dense files may need splitting.

## GPU memory policy

The installed CUDA PyTorch build is **2.6.0+cu124**, matched with torchvision 0.21.0 and torchaudio 2.6.0. Compact models run in separate processes, one after another:

- Faster Whisper **large-v3-turbo**, multilingual GPU **int8_float16**, 15-second windows and beam size 3. Uses Whisper's built-in silence checks; the separate CPU Silero VAD model is disabled. The 128-bin preprocessing configuration is downloaded with the weights. Speech uses CTranslate2 directly, avoiding an unnecessary PyTorch CUDA context.
- Qwen3 **4B Instruct 2507**, **Q4_K_M**, all layers on GPU, 4,096-token context, batches of 32 / microbatches of 16, f16 KV cache, Flash Attention off, one request slot, and host prompt cache disabled. The English-only emotion classifier is skipped for new reports.
- BLIP captioning **base**, GPU **float16**, one sampled frame at a time with greedy decoding.

Processes exit between stages to release GPU allocations. PyTorch workers have an allocator limit below the selected target. A watchdog samples **total GPU memory**, including other programs, and stops this app's worker at a guard threshold 256 MiB below the target. Any model failure, monitoring failure or safety stop aborts the job without CPU fallback. CTranslate2 has its own allocator and is governed by the watchdog, not the PyTorch allocator limit.

This is a conservative application target, **not an operating-system-wide hard cap**. Sampling may miss very brief peaks; other apps can use memory independently. The report records the observed total-GPU peak and actual device used for each model. Memory budget is not an accuracy score or utilization target. GPU utilization can briefly reach 100% even below the memory target; the app bounds work units and pauses between them rather than promising a fixed utilization percentage.

Full TRIBE fMRI inference is not part of this profile. The original `analyze_video.py` and scientific notebook remain available separately; their output is not used to invent marketing scores.

A longer continuous-generation check reached the 82 C guard and was stopped; bounded requests and temperature-aware pacing reduce sustained heat. Runtime flags were checked against the installed binary and the [official llama.cpp server documentation](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md).

Verification on this laptop: 58 studio regression tests passed. The failed `IMG_1273.MOV` review was recovered: nine valid saved sections were reused and the remaining four edits completed in 132.8 seconds, with a sampled GPU-memory peak of 3,053 MiB. All three GPU-rendered clips and the PDF exported successfully in another 10.2 seconds. These are recovery timings, not a fresh full-video benchmark.

That failure was a schema mismatch (`add` versus `insert`), not a CUDA crash. Safe edit synonyms are normalized, the prompt lists valid operations, and worker failures now surface their actual cause instead of labeling every error a GPU failure.

The video renderer uses the [NVIDIA FFmpeg hardware path](https://docs.nvidia.com/video-technologies/video-codec-sdk/13.1/ffmpeg-with-nvidia-gpu/index.html). Unsupported codecs/profiles or GPU rendering failures are reported per clip; the application does not silently switch to a CPU video encoder.

## OCR, Hinglish and compact reports

The current offline profile uses faster-whisper **large-v3-turbo / int8_float16** on CUDA, **RapidOCR 1.4.4 / ONNX Runtime** on CPU, optional BLIP frame descriptions, then **Qwen3-4B-Instruct-2507 / Q4_K_M** on CUDA. The existing 4B reviewer fits this laptop with more headroom than a 7B model. Model downloads require internet during setup; inference sends no video, transcript or frames to an external API.

Select **Auto detect / mixed speech** for Hinglish, or the known original language. ASR explicitly uses `task="transcribe"`; translation is not requested. An Indian English/Hinglish vocabulary prompt and per-window hotwords supply context without replacing recognized words by a dictionary. Word timestamps split long ASR paragraphs into sentence or roughly five-second spans for precise edit ranges. Check actual names and mixed speech against the audio: a prompt cannot establish transcription accuracy.

S1, S2, etc. identify speech; O1, O2, etc. identify on-screen OCR. Both are accepted as rating evidence. OCR lines below 0.90 recognizer confidence remain in the raw archive but are excluded from scoring evidence. This threshold is a heuristic, not a validated accuracy probability. Artificial line separators are normalized, and comment-keyword-link actions are detected explicitly. Validation rejects grading rationales that blame recognition noise on the creative. A clear `COMMENT [KEYWORD] FOR LINK` overlay supplies a CTA even when closing speech is incomplete. Natural phrases such as ?paisa vasool? and ?salon bhaiya? are not language errors. Product labels outrank conflicting generic scene captions, but OCR does not prove a product claim or long-term result.

The bundled OCR recognizer covers Latin/English and Chinese, **not all Indic scripts**. Romanized Hinglish is retained; Hindi/Tamil/Telugu-script overlays still require a native check. Sampling can miss brief stickers, small labels and stylized text. The UI exposes the source frames for verification. Do not interpret missing OCR as missing creative content.

A completed report offers `evaluation.json` with `narrative_breakdown`, `detected_on_screen_elements`, `linguistic_review` and `performance_score`, plus the rubric and uncertainty range. Scores are computed from weighted grades, then adjusted for confidence in the cited speech/OCR; the language name is never a scoring input. No labeled human dataset was supplied, so agreement rates and virality prediction accuracy remain unmeasured.

The downloadable PDF is **four pages**: decision/scorecard/best moments, narrative/screen evidence, priority changes below 70 (or final checks), and grade explanations with viewer-response bottlenecks or optional brand/reference findings. Screenshots are embedded rather than linked. PDF rendering checks both content overflow and page count before replacing the saved file. The full source evidence and edit plan remain in Studio and JSON.

VRAM stays on the conservative 4 GiB application target (3.75 GiB watchdog threshold), leaving headroom inside the 6 GiB card. Raising the budget alone would not improve detail. Video preparation and OCR also run in isolated CPU workers to release decoder, plotting and ONNX allocations before the next stage. Worker termination releases each runtime's allocations more completely than PyTorch `empty_cache()` alone, which cannot release CTranslate2 or llama.cpp allocations. No overclocking or global power changes are applied. Zero thermal throttling cannot be guaranteed from application code. Per-stage `telemetry_*.json` records elapsed time, sampled total-GPU memory peak and peak temperature; this is not proof that no brief peak or throttling occurred.

## Run or reinstall

From the project root:

```powershell
.\.venv\Scripts\python.exe studio_server.py
```

For a fresh Python 3.11 environment:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[studio,analysis,plotting,training]" -c constraints-local.txt
.\.venv\Scripts\python.exe prepare_gpu.py
.\.venv\Scripts\python.exe prepare_review.py
```

`prepare_gpu.py` targets Windows/Python 3.11 and verifies the pinned CUDA wheels and large model files against SHA-256 digests from the official repositories. Keep the local `.env` private. A replacement token can be entered there; the upload interface never displays it.

Tests: `.\.venv\Scripts\python.exe -m unittest discover -s tests -v`.

Model references: [Faster Whisper](https://github.com/SYSTRAN/faster-whisper), [BLIP base](https://huggingface.co/Salesforce/blip-image-captioning-base), [Emotion English DistilRoBERTa](https://huggingface.co/j-hartmann/emotion-english-distilroberta-base). Creative indices are the app's disclosed rules, not metrics published by these model authors.

The review installer downloads checksum-verified [Qwen3 Instruct](https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507) weights via [Unsloth Q4 quantization](https://huggingface.co/unsloth/Qwen3-4B-Instruct-2507-GGUF), the official llama.cpp CUDA runtime, and [Faster Whisper large-v3-turbo](https://huggingface.co/dropbox-dash/faster-whisper-large-v3-turbo). The new models require about 4.1 GB of model storage. Downloads occur during setup; customer video/transcripts remain local during review. Synthetic language integration tests explicitly use public test text with Google TTS; they are separate from production uploads.

## Regional-language accuracy and corrections

New transcriptions use Faster Whisper **large-v3-turbo** in GPU int8/float16. The earlier medium model produced a poor Telugu synthetic transcript and was replaced; historical reports retain their actual model name. Language support is not proof of equal accuracy across dialects, noise conditions, or code switching.

Under **Original-language transcript**, expand **Correct transcription errors and regenerate the review**. Fix the actual spoken words and save. Studio preserves the source timestamps and original input, invalidates cached review sections, and regenerates its assessment without rerunning speech or changing the video. Use this for misheard names, ingredients and regional-language words. Suggested marketing copy still requires a fluent editor and verification of product claims.

The report generator decodes complete token sequences across its small GPU requests, preventing split Unicode characters from turning into replacement symbols. Native Hindi/Tamil/Telugu round-trip generation is included in the GPU runtime probe. PDFs use browser shaping and local fonts for native-script text.

The full large-v3 model exceeded the available Windows RAM during loading; the turbo variant uses fewer decoder layers and smaller weights. The 4 GB GPU target, GPU-only inference and RAM reserve remain in force.

Speech decoding uses temperature zero; stochastic fallback generated spurious text in the synthetic Tamil check. Hindi/Tamil/Telugu GPU checks now run below 1.4 GB total observed VRAM, but synthetic tests are not a benchmark of dialect or customer-video accuracy. Review loading uses `--load-mode none --no-host` to avoid the large Windows RAM spike observed with memory-mapped loading, while retaining full GPU layer offload.

## Estimated score when language recognition is uncertain

The headline is now an **estimated creative score**, with the original rubric score and sensitivity range displayed alongside it. For each category, Studio uses recognizer confidence from the transcript segments cited by that category. It blends the category score toward a neutral 50 as evidence becomes uncertain, reducing both penalties and praise. It uses the same calculation for every language, including English; there is no regional-language bonus or automatic score above 70.

For each cited segment, the evidence weight is the minimum of 1, `(mean word confidence - 0.35) / 0.45`, and `2 × fraction of words with confidence >= 0.60`, clamped at zero. Missing confidence gets weight 0.5. Team-corrected transcripts get weight 1. Category weights average cited segment weights equally, avoiding differences in language tokenization. An explicit, non-negated mention of recognition/transcription errors, uncertainty, misheard or mistranscribed speech in a category rationale caps its evidence weight at 0.5. This catches some confident recognition errors; it is a conservative text rule, not an independent language verifier. The adjusted category score is `weight × raw category score + (1 - weight) × 50`; the eight category importance weights produce the final total.

The sensitivity range allows the unknown portion to take any score from 0–100, then adds an eight-point editorial allowance. These constants and the neutral 50 are transparent assumptions, **not calibrated performance statistics**. Confident mistranscription or cultural misunderstanding can still bias a review. A very wide range means “verify the transcript,” not “this video is average.” The edit plan remains based on the underlying rubric and is provisional when recognition is weak. Correct the transcript and regenerate before making costly editing decisions. Real watch time, retention, shares and conversions are needed to validate marketing performance.

Latest verification (17 October 2026): the saved 58.6-second sample receives a 50/100 estimated creative score, down from 65/100 after adding voice and visual evidence and enforcing a real CTA. Its four-page PDF includes eight evidence-linked grade explanations, four viewer-response hypotheses, key transcript/overlay moments with timestamps, and embedded video screenshots. The expanded PDF reuses saved analysis without another model run. Peak sampled total GPU memory during the original analysis was 3,522 MiB. Proposed wording, timing and product claims remain editorial suggestions to verify in the actual edit.

## Optional brand briefs, successful references and team learning

Open **Brand context and successful references** below the upload settings. Everything remains optional: **No brand context** keeps the general creative review.

1. Create a brand or choose a saved one. Separate profiles keep each brand's documents, references and feedback apart.
2. Expand **Optional brand guidelines and product brief**. Upload a PDF, DOCX, UTF-8 TXT or Markdown file, or paste/edit its text. Click **Save brand documents**; pending document edits are also saved when you analyze a video. Each document supports 5 MB and 12,000 extracted characters. Documents beyond the limit are rejected rather than silently truncated. Scanned PDFs require selectable text or pasted instructions. Extracted text is retained locally.
3. To add a winning video, choose **A successful reference to learn from**, use the main video uploader, and optionally supply a team rating, views, average viewed percentage, conversions, spend, distribution type and notes. Its normal analysis runs once; after completion it becomes a reusable reference. You can also attach an existing completed semantic report by its 32-character report ID. Up to five active references can be kept per brand. Removing a reference keeps its video/report on disk.
4. Choose **A new video to evaluate** for the next candidate. Brand checks quote the supplied document, cite video transcript evidence, identify missing/conflicting requirements, and suggest corrections. Visual-only requirements without sufficient evidence are marked **unknown**, not silently failed. Reference comparisons use bounded opening/closing transcript excerpts and stored category grades; they do not rewatch all reference footage or establish why it succeeded.
5. After publishing, open **Teach future reviews** in the report and enter your team's rating and actual results. Saving again replaces that video's feedback rather than counting it twice. Include average and weak candidates as well as winners. Notes inform later editing advice; actual performance numbers appear in reference comparisons with their distribution context.

With brand checks, the headline combines **70% language-adjusted creative assessment + 30% brand alignment**. Brand checks have equal weight; an unknown check contributes a neutral 50 and broadens the sensitivity range. Both component scores and evidence coverage are shown. Without brand requirements the creative component is retained. Similarity to a winning reference does not automatically earn points, and brand-supplied product claims still need verification.

Feedback calibration is deliberately separate from model training. After **five distinct candidate videos** with team ratings spanning at least **20 points**, later uploads can receive a brand-specific correction: mean(team rating minus the uncalibrated overall) × n/(n+10), capped at ±10 points. Successful references, including references later removed from the active set, are excluded from this correction. Views and conversions are observations, not labels for this calibration; raw views alone mix creative quality with audience, paid distribution and posting conditions. Model weights are not fine-tuned. This keeps memory within the existing GPU budget and avoids treating a handful of winners as a validated prediction model.

Each upload saves a versioned brand snapshot. Later document edits and feedback affect future uploads; existing reports retain their original basis. Reports and PDFs include the brand checklist, comparisons, available reference screenshots and calibration explanation. PDFs continue to embed screenshots rather than clip links.

Byte-identical uploads are identified by a SHA-256 fingerprint. Reuploading the same file does not create another independent calibration example, and its earlier feedback/reference is excluded when assessing that same file. Different encodings of the same creative may still need manual deduplication. Reference outcomes can also be updated under **Saved successful references → Update reference results**.

If a grade-zero criterion has no positive source citation, the report explicitly identifies the full transcript as the **absence-check search scope**. Invalid source IDs remain rejected. Repetitive generated copy is detected early; if an edit fails twice, the saved ratings still export with a clearly labeled fluent-editor checklist for that edit. A failed native rewrite is never presented as verified copy.

Brand-feature verification (30 September 2026): 87 regression tests passed. An isolated browser workflow verified document upload, reference analysis/registration, editing reference outcomes, candidate assessment and saved team feedback, with no browser errors or mobile overflow. Its 12-page PDF contains embedded images and zero link annotations. That browser workflow uses a synthetic analysis fixture; GPU generation is checked separately by `tests/run_brand_gpu_probe.py`.

The GPU integration check passed using the actual local CUDA reviewer with synthetic brand/reference evidence: two brand checks and one comparison with independently validated current/reference source IDs, peaking at 3,068 MiB total observed GPU memory. This validates the execution path and resource use, not marketing prediction accuracy.

### Citation recovery

When a rating or edit omits its source IDs, Studio makes a small local evidence-selection request while preserving its assessment and proposed wording. Only supplied IDs are accepted. Unsupported/empty selections remain validation failures; no sources are invented or silently borrowed from a previous rating. The raw review records citation repairs. Completed sections and in-progress generation remain resumable.

Checkpoint results are kept separately for each prompt attempt. A failed initial attempt therefore cannot overwrite the saved corrected retry. Results are reused only with matching model/input signatures and prompt hashes, and still pass the current validation checks. Job status writes are flushed to disk before replacing the previous status file.

Brand documents up to 900 input tokens are assessed in one prioritized pass. The one-view report keeps the five requirements with the largest publishing impact, favoring explicit must-haves, must-not rules, required claims, product identity and CTA instructions. Longer documents split automatically. This is a priority check rather than an exhaustive compliance audit; incomplete JSON is never scored. The GPU context and memory budget remain unchanged.

Review inference uses the 75/72 C cooling thresholds and temperature-dependent burst sizes above. Short NVENC clip exports use the dedicated video engine and the 76/74 C preflight thresholds; their live 82 C stop remains enabled.

GPU monitoring reads the NVIDIA driver directly (NVML) without loading an inference model or launching a subprocess per sample; nvidia-smi remains a fallback. The 82 C emergency stop remains active; the GPU target is now detected automatically. `review_profile.json` separates inference request time, monitoring/cooling time, and cache hits. Inspection and OCR also save stage timings. No fixed 5-10 minute completion time is guaranteed for long videos, dense briefs, or hot/busy systems.


## NVIDIA Nemotron content writer

Set `NVIDIA_API_KEY` in the server environment or the ignored project `.env`, then restart Studio. In Script Writer, select **NVIDIA Nemotron 3 Ultra**. When a key is configured, new browser sessions default to NVIDIA; saved briefs keep their chosen engine. Local remains available. Never put a real key in source files or Git.

The model is `nvidia/nemotron-3-ultra-550b-a55b`, using NVIDIA's OpenAI-compatible streaming endpoint at `https://integrate.api.nvidia.com/v1/chat/completions`. No additional SDK is required. NVIDIA receives the brief, selected references and previous script when revising. Usage limits and account charges depend on NVIDIA; this integration does not buy credits or silently switch providers.

Nemotron handles hook creation, critiques, full scripts, paragraph revisions and Suggest changes through the existing persona and editorial review pipeline. Creative calls use temperature 1 and top-p 0.95; critique and repair calls use temperature 0. Thinking uses the medium reasoning-effort setting; only final spoken content enters the live preview, never reasoning. Output is bounded to 4,096?8,192 tokens per call and 24 calls per run. Checkpoints and usage metadata are separate from HF/local, with no credentials saved. Connection/quota failures preserve saved drafts and allow an explicit retry with Local. The 80+ score remains an editorial target, not a guarantee of audience performance.

API reference: https://docs.api.nvidia.com/nim/reference/nvidia-nemotron-3-ultra-550b-a55b-infer


## Natural creator scripts and language support

Choose a **Content niche** or let the writer detect skincare/haircare, fashion, arcade, food/drinks or household FMCG. The Creator reference scripts section contains two source-linked patterns per niche and 30 original practice scripts across English, Hindi and Hinglish. Sources distinguish actual creator clips, long-form references, interviews, third-party view indexes and reported campaigns. Indexed or reported views are historical evidence, not independently verified current metrics. Some references have no verified individual reach and are explicitly marked that way.

The writer retrieves two matching examples in the requested language for hooks and drafts. It learns conversational rhythm from those examples at inference time; no Nemotron weights are fine-tuned. Public full scripts, creator catchphrases and unlicensed video transcripts are not redistributed. The complete original practice scripts are in `script_examples.json`; they are not claimed to be viral winners. Run `.venv\Scripts\python.exe prepare_script_references.py` to download the referenced public pages into the ignored `cache/writer/reference_sources` directory. The manifest records failures, titles, timestamps and checksums. These page downloads are not video transcripts and do not enter prompts automatically.

Language choices include **English**, **Hindi** (Devanagari), **Hindi (Roman)** and **Hinglish** (Roman Hindi-English). Other language entries remain supported through the existing free-text field. Hindi is drafted directly rather than by translating an English ad. The writer checks the selected writing system, basic Hindi-English mixing, duration and speech density. Hindi uses an approximate 1.8-2.8 words/second budget; English and Hinglish use 2-3. English read-time estimates retain the prior 120-160 words/minute range. All timing remains approximate: confirm with a read-aloud.

For NVIDIA organic/UGC drafts, a separate native-language voice edit runs before scoring. It changes speech only, preserves paragraph times and targeted revision scope, and counts against the hosted call limit. If it cannot complete, the original generated draft is retained with a review blocker. Medium reasoning is used to reduce unnecessary deliberation, with no fixed latency guarantee.

The organic review now flags stock ad phrases and ornate phrasing such as silent vows and invisible armor. A valid JSON response can still receive a sub-80 score if it sounds synthetic, uses the wrong writing system or misses duration. Revision keeps the best saved draft and the existing attempt limit. Automated language and style heuristics can miss errors; review the final copy before recording.

## Kumo performance estimates from your real posts

Kumo Relational is connected separately from the writing model. Configure `KUMO_API_KEY` in the ignored `.env` or server environment; it can fall back to `NVIDIA_API_KEY`. It does not train Nemotron or rewrite scripts. It estimates the chance of meeting **your defined outcome**, using structured pre-publication speech features and labeled examples from your own account. The editorial 80+ target remains separate.

Download the JSON template in **Your post outcomes**, fill it with real posts, and import it. Imports replace the previous account dataset. Use one account, one measurable rule and one fixed observation window of 1-720 hours. A row includes `post_id`, `niche`, `language`, `platform`, `duration`, original `script_text`, timezone-aware `published_at`, timezone-aware `observed_at` and boolean `label`. Label true means that post actually met your rule; false means it did not. Do not use model scores, made-up outcomes or only successful posts. Outcomes must already be observed after the complete measurement window.

After generating a script, click **Estimate with Kumo**. It uses current editor text and requires at least 20 posts in the same niche, language and platform, with duration within 5 seconds, including at least 5 successes and 5 misses. This is a conservative application gate, not a claim of statistical sufficiency. At most the latest 200 matching posts are sent. The displayed probability is experimental and uncalibrated: it has not been validated on held-out posts. The historical base rate and number of examples are shown alongside it.

Only numerical speech features, a first-person indicator, dates, synthetic row IDs and historical labels are sent to NVIDIA. These features include duration, word count, opening length, mean sentence length, question count and stock-ad-phrase count. Raw script text, account name, product facts, outcome rule text, views and other post-outcome measurements are not sent as input features. The script's meaning, delivery, visuals and audience are not modeled by these simple features. Never interpret the estimate as a calibrated viral prediction or as proof that changing a word causes performance. The prediction does not alter the draft, editorial grade or revision ranking. API failures leave the draft intact and do not retry automatically.

Reference API: https://docs.api.nvidia.com/nim/reference/nvidia-kumo-relational-statuspolling


## Topic research with Meta Muse

Set `MUSE_API_KEY` in the server environment or ignored `.env`. Existing `NVIDIA_API_KEY` is a fallback. In Script Writer, use **Topic research with Muse**: enter a topic, or leave it blank to use the brief topic. It takes the selected niche, language and platform, searches recent public news RSS snippets, and calls `meta/muse-glimmer-30b` via NVIDIA. No additional SDK or paid search subscription is required; NVIDIA account usage limits still apply. The request uses temperature 1, top-p 0.95, 8,192 maximum tokens, medium reasoning and non-streamed output. Only final research text is retained, never reasoning or credentials.

Muse returns source-linked observations, three creative angle suggestions, audience questions and cautions. Sources are snippet-level evidence, not verified article bodies, creator transcripts or measured viral successes. Search is requested for the last 90 days, but review the returned dates and sources yourself. If search is unavailable, the tool explicitly uses historical curated format notes and warns that they are not fresh topic evidence. Failed synthesis preserves retrieved sources and requires a manual retry. No hidden inference retries run.

Research runs in its own single remote-job slot and can run while GPU analysis is busy. Completed dossiers are saved in ignored `results/_research`. Open one from the saved list and select **Use these notes in my script brief**. Attaching notes fills the topic and niche. The server checks that notes match the topic and niche and supplies a bounded unverified `research_context` to the script writer and its reviewer. Research never fills verified product facts or becomes efficacy proof. Deselect the checkbox to omit it. This is source-assisted in-context learning, not weight fine-tuning. Topic searches are sent to the public news service; topic metadata and selected snippets are sent to NVIDIA.

## Maximum local GPU mode

The UI selects the maximum detected target automatically. `0` on the pipeline CLI also selects automatic mode; explicit smaller budgets remain supported. On a 6,144 MiB GPU this resolves to 5,632 MiB total device usage, with a worker stop threshold another 256 MiB below that target. Other GPUs derive their target from total VRAM, rounded down to 256 MiB after reserving 512 MiB for the desktop. Existing API clients may still request 4,096 MiB explicitly.

At targets of at least 5,120 MiB, local review/writing uses an 8,192-token context and 128/64 batch/micro-batch instead of the smaller 6,144-token, 32/16 configuration. Full GPU layer offload remains enabled. Model stages still run sequentially, free-memory checks remain active and hot GPUs still pause or stop. Higher allocation headroom does not require filling VRAM and is not a promise of lower latency, especially during thermal pauses.

Muse API reference: https://docs.api.nvidia.com/nim/reference/meta-muse-glimmer-30b-infer


Video mechanism learning: open the writer's Muse research panel, select the brief language/niche and optionally provide direct video links or upload reference clips. Discovery prioritizes YouTube short vertical candidates, TikTok, then Instagram. It compares observed view snapshots within available candidates; private/restricted videos are skipped. Local Whisper transcribes actual speech in the shared GPU slot, followed by Muse analysis grounded in timestamps and book principles. Rules are saved in results/_writer_learning and recalled for the same niche/language. Practice scripts are no longer sent as writing templates. This memory guides inference and does not fine-tune model weights. Hindi ASR and generated copy should receive a native-language review.

The team engine uses GPT-OSS 20B for rough writing and Gemma 4 31B for analysis/voice edits. No shot list or subtitle instructions are generated. NVIDIA model outages fail visibly with saved drafts retained. A configured key confirms configuration, not live service availability. Kumo needs actual comparable account outcomes; no public-view-to-success labels are synthesized.

TRIBE recording ratings: export actual predictions using TRIBE_CALIBRATION_GUIDE.md into the completed video job as tribe_prediction.npz/json, and set TRIBE_CALIBRATION_ARTIFACT to a fitted calibration artifact. The writer's recording-rating control checks the original video hash, language, feature names and inference signature before applying calibrated dimensions. Editorial 80/100 is not a TRIBE score or a guarantee of virality.
