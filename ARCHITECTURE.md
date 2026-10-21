# Hosted actor-critic and audio-visual review

## Script contract

`generate_viral_script_pipeline` in `studio_pipeline.py` runs exactly three logical stages for a multi-format request:

1. Actor: `{"final_script":"continuous script"}` with duration, verified brief, bounded reference cards and retrieved creator personas.
2. Mechanical self-critic: arrays named `hook_velocity`, `visual_pacing`, `no_fluff`, `direct_response_strength` and `safety_issues`. Counts and deterministic findings accompany the draft. No remote pass/fail score is requested.
3. Editor: `script_body` plus three `{kind,text}` hooks in problem, curiosity, contrarian order. The editor receives the critique and requested edits.

The server composes each hook with the same body, preserving the opening visual on the first line. All variants receive deterministic length, format, CTA and product-safety checks. Approval means these checks passed; it is not an independent quality score. A failed API/schema/check stage retains completed work without an automatic grading or rewrite loop. Checkpointed successful stages can be reused during a manual retry. Archived scene-format work retains compatibility helpers.

The selected hosted writer handles all three roles, switching system instructions rather than models. Thinking remains enabled. `studio_script_team.py` centralizes SSE, queued-response polling, 15-second application progress heartbeats and a 180-second per-call deadline. One fresh client is permitted for transient connection failures or HTTP 500/502 within that deadline. Authentication, quota and other HTTP failures are not automatically retried. Progress heartbeats do not inject data into NVIDIA's upstream connection.

## Persona lookup

`studio_persona_lookup.py` builds a cached sparse TF-IDF cosine index from the persona Markdown table. It retrieves at most two records by default, with explicit persona selection taking precedence. This bounds prompt growth without another API call, a vector service or model download. This is a small local retrieval implementation informed by NVIDIA RAG guidance, not a deployment of NVIDIA RAG Blueprint. References teach through prompt context; model weights are unchanged.

## Video evidence and simulation

`extract_media_parallel` uses `asyncio.gather` and worker threads to overlap FFmpeg JPEG extraction with audio extraction and Whisper transcription. The mono PCM16 WAV is 16 kHz. Whisper word timestamps support clip-wide WPM and speech-free intervals over one second. Speech-free does not mean acoustically silent. Corrected transcripts retain only available timing evidence.

`simulate_cognitive_response` sends actual JPEG `image_url` content, the transcript, word timings and WPM to `nvidia/nemotron-3.5-super-vl-120b-a12b`. This VL model has no audio encoder: speech reaches it as Whisper text and measured timing data, not raw sound. NVIDIA documents multimodal image input in its [Nemotron 3.5 Super VL guide](https://docs.nvidia.com/nim/large-language-models/latest/get-started/advanced/get-started-nemotron-3.5-super-vl.html).

Required output fields are `attention_retention_score`, `emotional_arousal_state`, `cognitive_load_warning` and `psychological_critique`. Optional timestamped failures and observations must cite supplied frame timestamps. Scores are uncalibrated editorial hypotheses. Sampling can miss events between frames; ASR can mishear words. Missing evidence is retained explicitly. There is no local fMRI/TRIBE inference.

The active upload route invokes one unified review instead of a redundant visual-only review followed by another simulation. SHA-256 checks guard against reporting evidence for an MP4 replaced mid-review. Partial audio/transcript evidence survives cloud failures.

## Conditional audit

Attention below 70 triggers one three-stage actor-critic revision and a PDF. At 70 or above, no automatic revision/PDF is generated. FFmpeg extracts supplied failure timestamps exactly; screenshots are factual evidence, not generated illustrations. ReportLab uses three bounded pages and a canvas page-number guard: critique, visual evidence, then side-by-side transcript and revision. Failed revisions are labeled for further review and do not become approved merely because a PDF exists.

## Integration scope

Official `nemotron-customize`, `rag-blueprint` and `accelerated-computing-cudf` skills are installed locally; provenance is recorded in `skills-lock.json`. No fine-tuning, full Blueprint services or GPU DataFrame workload is deployed. A few sampled frames and persona records do not justify cuDF overhead. API inference remains hosted. Optional existing cached CPU Whisper is transcription, not local virality reasoning.

Live tests and generated evidence are kept in ignored `results/` directories. They verify connectivity and contracts, not future viral performance or purchase intent. Stage timings include provider reasoning and queueing, so the three-call pipeline does not guarantee a fixed overall latency.
