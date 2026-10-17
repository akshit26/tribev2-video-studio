# Local creative report studio

Double-click **Start Studio.cmd** in the folder you cloned or downloaded. It starts the local server and opens <http://127.0.0.1:8765>. Keep using that address; opening `web/index.html` directly cannot run analysis. Double-click **Stop Studio.cmd** to stop this project's server and its active model workers. Saved reports are kept. Reopen an interrupted job and use **Resume saved analysis**; completed review sections are reused. In-progress token output is also checkpointed after each burst and resumed only when its model/input/prompt signature matches. New machines should first follow [TEAM_SETUP.md](TEAM_SETUP.md).

From the VS Code terminal (PowerShell), in the repository root:

```powershell
.\.venv\Scripts\python.exe studio_server.py
```

Leave the terminal open, visit <http://127.0.0.1:8765>, and press **Ctrl+C** in that terminal to stop an idle server. For an active job use **Stop Studio.cmd**. Opening the server does not start model inference.

### Fast GPU processing with temperature-aware pacing

Speech, sampled-frame descriptions and text review use sequential GPU workers, without automatic CPU fallback. RapidOCR runs deliberately on CPU/ONNX between these stages to preserve GPU headroom. File handling, decoding, tokenization and PDF export also use CPU/system RAM. The earlier review runtime logged a CUDA illegal-memory-access crash; the new review configuration uses full layer offload, smaller requests and plain f16 cache with Flash Attention disabled. A short guarded runtime check cannot guarantee that every future video or driver state will be stable.

The GPU target is fixed at **4 GB total usage**, including other applications. The watchdog stops the current model at **3.75 GB**, leaving about 2 GB or more on this 6 GB GPU for the desktop and brief spikes. Review inference pauses between work units at **75 C** and resumes at **72 C or lower**; a running worker stops at **82 C**. Cooling waits are limited to two minutes. These are conservative application settings, not manufacturer temperature specifications or hard system-wide limits.

Jobs and model stages require **1.5 GB available RAM**; running model workers stop below **768 MB**. A safety stop fails the job and terminates its worker tree instead of retrying on CPU. Completed stages are reused when the job resumes. No system-wide GPU power or clock settings are changed. Sampled guards cannot prevent every instantaneous allocation spike or driver crash.

Execution order:

1. Measure the video and audio.
2. Transcribe speech using 15-second windows, one worker, with pauses between returned segments.
3. Terminate the speech worker to release CTranslate2 allocations. Run local RapidOCR at 0.8 fps, with bounded extra probes around the largest measured visual changes and the final frame. Near-duplicate overlays are deduplicated. Keep the timestamped original text and frame crops without translation. Describe diverse sampled frames even when OCR is plentiful, and measure audio variation from the actual decoded waveform.
4. Terminate the caption worker. Give the text reviewer speech, OCR, audio measurements and secondary sampled-frame descriptions, then generate a concise narrative and strengths. The text model does not receive pixels directly; uncertain captions must not override a legible product label or CTA. Audio variation is not a direct measure of emotion.
5. Rate all eight criteria in a bounded batch; regenerate only unsupported individual ratings.
6. Generate each exact edit in a separate request, covering every weak criterion.
7. Unload the review model, then decode, resize and encode clips using NVIDIA NVDEC, CUDA scaling and NVENC H.264. Clips are rendered sequentially with GPU memory/temperature monitoring. Audio encoding, small measurements, file I/O and PDF layout still use the CPU; those operations cannot all be transferred to CUDA.

The reviewer uses a 6,144-token GPU context with compact source metadata, preserving the original speech and OCR for ordinary short ads without summary calls. Longer evidence is condensed with exact CTA/label excerpts retained. Review bursts adapt to temperature: prompt/output limits are 96/32 tokens below 68 C, 48/16 below 72 C, and 24/8 when warmer. Shared evidence stays cached in the current GPU slot. There is no fixed delay when below the pause threshold. At 75 C the reviewer waits until the GPU cools to 72 C; warm bursts stay small to leave headroom. The 82 C stop guard stays enabled. This replaces the old three-second pause on every request. Throughput depends on cooling and competing applications; no fixed completion time is promised. The review model and its current GPU context stay loaded between bursts but is not generating during those pauses. Completed sections are checkpointed with an input signature. After a failed run, click **Resume saved analysis** to reuse the saved upload, transcript, frame evidence and valid completed review sections. Input or prompt changes invalidate the corresponding checkpoints. The model retries only a failed section rather than regenerating every valid section. Exceptionally dense transcripts are summarized in bounded sections, so compressed evidence can lose nuance. The original transcript remains available in the report.

1. Drop a video into the upload box.
2. Leave **4 GB** selected. This is the fixed conservative target on your 6 GB GTX 1660 Ti; the previous 4.5/5 GB choices are disabled.
3. Choose the speech language (or Auto), platform and optional audience. Keep visual descriptions enabled for additional sampled-frame evidence.
4. Click **Analyze video**. After completion, read the detailed review and exact edit plan, play or download the clips, and use **Download PDF**.

Videos stay on this computer. The first use may download model weights from Hugging Face; the video is not sent to an external inference service. One video is processed at a time. Uploads are limited to 250 MiB, 10 minutes, and at most 4K pixel count. Reports and source uploads are saved under `results/studio/<job-id>/`.

## Detailed multilingual review

Choose Auto detect for supported mixed speech, or set the main language manually: Hindi, Tamil, Telugu, Bengali, Marathi, Gujarati, Kannada, Malayalam, Punjabi, Urdu, Assamese, Nepali, Sanskrit, Sindhi, or English. The selector reflects Whisper's language IDs, not a claim of equal accuracy. Odia and unlisted regional languages/dialects do not have an explicit profile in this model. Always have a fluent speaker check the original-language transcript and replacement wording.

Select a platform and optionally describe the audience and objective. The review explains its reasoning in English, while suggested spoken lines/overlays use the transcript's language and include an English gloss. Automatic detection can still miss short code switches, names and dialect words. Use the manual language override and re-analyze when detection is wrong.

The overall creative score comes from a local semantic review. Eight fixed criteria are graded 0-4: hook (15%); script/message (15%); structure/pacing (10%); credibility (10%); emotional relevance (5%); CTA (10%); voice/delivery (15%); visual presentation (20%). Every judgment cites supplied speech, OCR, audio or sampled-frame evidence. The app validates source IDs and grades and computes the total independently. Readable captions alone do not establish visual quality, and a catchy slogan is not an actionable CTA.

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

The downloadable PDF is **three pages**, or **four with brand context**: decision/scorecard/best moments, narrative/screen evidence, priority changes below 70 (or final checks), and optional brand/reference findings. Screenshots are embedded rather than linked. PDF rendering checks both content overflow and page count before replacing the saved file. The full source evidence and edit plan remain in Studio and JSON.

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

Latest verification (17 October 2026): the saved 58.6-second sample receives a 50/100 estimated creative score, down from 65/100 after adding voice and visual evidence and enforcing a real CTA. Its four-page PDF includes eight evidence-linked grade explanations, key transcript/overlay moments with timestamps, and embedded video screenshots. The expanded PDF reuses saved analysis without another model run. Peak sampled total GPU memory during the original analysis was 3,522 MiB. Proposed wording, timing and product claims remain editorial suggestions to verify in the actual edit.

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

Review inference uses the 75/72 C cooling thresholds and temperature-dependent burst sizes above. Short NVENC clip exports use the dedicated video engine and retain a 76 C preflight threshold, cooling to 74 C when necessary; their live 82 C stop remains enabled.

GPU monitoring reads the NVIDIA driver directly (NVML) without loading an inference model or launching a subprocess per sample; nvidia-smi remains a fallback. The 82 C emergency stop and 4 GB target remain active. `review_profile.json` separates inference request time, monitoring/cooling time, and cache hits. Inspection and OCR also save stage timings. No fixed 5?10 minute completion time is guaranteed for long videos, dense briefs, or hot/busy systems.
