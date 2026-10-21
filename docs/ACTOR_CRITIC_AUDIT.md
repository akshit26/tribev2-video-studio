# Creator Studio architecture audit — 2026-10-21

## Verified implementation

- Multi-format writing uses draft, mechanical self-critique and editor stages, with three interchangeable hooks and one shared body. No final remote grade or automatic generation/rejection loop runs on this path.
- Reasoning remains enabled. Shared NVIDIA transport uses SSE, 15-second progress heartbeats, a 180-second per-call deadline and one fresh-client retry for transient connection failures or HTTP 500/502.
- Cached editor outputs that fail schema or deterministic safety checks are evicted. Manual retries can reuse completed actor/critic stages. System-prompt changes invalidate the checkpoint signature.
- Persona retrieval is a cached sparse cosine lookup over the Markdown reference desk, bounded to two records by default. It does not train weights or deploy the full NVIDIA RAG Blueprint.
- Uploaded video reviews overlap frame extraction with audio/Whisper work, then send actual pixels, transcript, word timings and WPM to Nemotron 3.5 VL. No redundant first visual-only API call runs.
- Attention below 70 triggers a three-stage revision and a PDF capped at three pages, with exact flagged screenshots and a side-by-side transcript/revision comparison.

## Automated and browser verification

`python -m unittest discover -s tests`: **358 tests passed**. Coverage includes transport failures/deadlines, schema validation, safety constraints, all duration modes, retries/checkpoints, evidence provenance, concurrent extraction, review failure recovery and PDF thresholds/page caps.

Seven browser workflows passed: writer editing/export/revisions, multi-format approval/recovery, cognitive metrics/audit download, optional cloud-review polling, brands/references/feedback, existing studio workflow, and the new three-hook selector. No JavaScript errors or mobile horizontal overflow were observed. Hook swaps preserve the body, opening visual cues, manual edits and saved selection.

Syntax checks passed for 43 `studio_*.py` files and four web JavaScript files. `pip check` found no broken requirements. The audit PDF was parsed and visually inspected; it has three pages and three embedded source screenshots. Extracted audio was verified as mono, PCM16, 16 kHz. Cached persona lookup averaged below 1 ms on this PC in a 1,000-query local sample.

## Live NVIDIA/Whisper evidence

A synthetic portrait video deliberately used a solid navy image, approximately ten seconds before speech, and Windows-generated speech describing a reusable silicone shower hair catcher. This tests the pipeline, not a real advertisement or purchase intent.

- Parallel media preparation took **15.8 seconds** and returned **41 word timestamps**, **92.6 clip-wide WPM**, and an opening speech-free interval ending at **9.78 seconds**.
- Nemotron 3.5 returned attention **10/100**, low-arousal boredom, and no cognitive-load warning. The low estimate automatically triggered a revision and the three-page PDF.
- The complete review, including three revision stages and PDF, took **271.8 seconds**. Revision stage times were approximately **16.2 / 95.7 / 97.1 seconds**. All three returned hooks passed deterministic checks.
- A separate Nemotron manual retry completed in **62.1 seconds**, reusing the cached actor and critic and calling only the editor. This is not a fresh full-pipeline speed measurement.
- A later fresh Nemotron check completed actor and critic in **34.6 / 76.2 seconds**, then received **HTTP 500 twice** at the editor. The configured single fresh-client retry ran, and the app retained the completed draft rather than crashing or falsely approving it. This confirms that provider failures remain possible even with resilient transport.
- Manually resuming that Nemotron request reused the two completed stages and called only the editor. It completed in **38.1 seconds**, returning a **45-word script** and **three distinct hooks**, all passing deterministic checks. This confirms recovery without restarting the pipeline; it is not a fresh full-pipeline speed measurement.
- A fresh GPT-OSS check completed all three API stages in **193.0 seconds** without a connection crash. Its output was correctly retained as unapproved for exceeding the word limit. Inspection also exposed unsupported personal-benefit wording and an interrogative without punctuation; additional guards and editor word-budget instructions were added. The final fresh recheck exceeded NVIDIA's **180-second deadline during the actor stage**. This exposed and fixed a pipeline bug that had replaced the real provider timeout with a generic no-draft error. The frontend now retains the actual diagnosis. GPT-OSS is not claimed to be consistently available or fast.

Generated clips, diagnostics and PDFs remain in ignored `results/` folders. Provider latency varies substantially. There is no controlled before/after speed comparison and no guarantee that future scripts pass checks, go viral or drive purchases. Explicitly flagged drafts remain recoverable; they are not presented as approved output. ASR errors and sparse visual sampling remain practical limits.
