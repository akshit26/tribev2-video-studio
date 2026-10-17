# Original-language TRIBE research workflow

Read [the pre-change audit](TRIBE_LANGUAGE_AUDIT.md) first. This is a separate,
opt-in workflow using TRIBE predictions and NumPy ridge regression. The running
Studio remains the explicitly labeled Whisper/BLIP/Qwen application. Its scores
are not imported as TRIBE features or human labels. No existing scores were changed.

**Current status:** language/ablation interfaces and offline calibration tools are
implemented. The user has no matched/native-rated dataset and requested skipping
collection. No language calibrator is fitted, no full TRIBE GPU inference was run,
and no language has a measured 80–90% agreement result. Hindi, Tamil, Telugu and
all other languages remain **unvalidated**, not automatically below 80%.

## Original inputs and ablations

The following requires a provisioned TRIBE installation, its checkpoint and stock
encoders. It is **not a command to run inside the 4 GB Studio budget**: full TRIBE
has not been verified to fit this workstation. A 3B text encoder alone is roughly
6 GB in FP16 before other allocations, and the installed standard CUDA loader
does not explicitly select that precision. AV-only memory also needs measurement.
Do not concurrently run this and Studio GPU analysis. No silent CPU fallback,
quantization or substitute encoder is supplied by this research workflow.

```python
from tribev2 import TribeModel

model = TribeModel.from_pretrained("facebook/tribev2", cache_folder="./tribe_cache", device="cuda")
# Pass the actual video. No translated audio, text input or dubbed copy.
events = model.get_events_dataframe(video_path="original.mp4", language="ta")
full, full_segments = model.predict(events=events, text_weight=1.0)
weakened, weak_segments = model.predict(events=events, text_weight=0.5)

# This route skips ASR and the text encoder altogether.
av_events = model.get_events_dataframe(video_path="original.mp4", language="ta", include_text=False)
av, av_segments = model.predict(events=av_events, text_weight=0.0)
```

Use explicit language codes when known: hi, ta, te, bn, mr, gu, kn, ml, pa, ur,
etc. `auto` requests detection and does not force English. Accepting a code does
not establish WhisperX ASR/alignment support for that language. The stock helper
still uses WhisperX large-v3 (part of the original TRIBE preprocessing dependency).
If no default aligner exists or word timestamps are missing, it fails clearly;
it does not silently translate, drop unaligned words, or invent word times. For
unsupported languages use AV-only and native-reviewed transcript spans, or supply
properly aligned native Word events to `predict`. Initial silence, mixed language,
names and dialects still need native checks.

Text contexts now concatenate original words, preserving script and wording,
instead of calling language-dependent spaCy sentence reconstruction. The old
English-default `.tsv` caches are not reused. New caches include language and audio
file size/modification time. Existing explicitly supplied Word events are trusted
as input; ensure they really contain the original speech.

Text weakening scales the projected branch after normalization. It is an
experimental ablation, not retraining and not a validated accuracy improvement.
Zero weight drops Word/Text/Sentence events so the loader removes their extractor.
Do not compare raw amplitudes as though lower amplitudes mean worse tone.

## Export ROI features with provenance

Provide a verified ROI mapping JSON with `vertex_count`, `vertex_order`,
`provenance`, and `rois` mapping each name to integer vertex indices. The exporter
does not guess which vertices are auditory/visual/language regions. For fsaverage5,
verify both hemispheres and the actual checkpoint output ordering against your
chosen anatomical/functional atlas. A language ROI is not automatically a tone ROI.

```python
from tribe_calibration.core import read_json
from tribe_calibration.workflow import export_prediction, file_hash

atlas = read_json("verified_rois.json")
# Use the actual local best.ckpt used to instantiate model above.
checkpoint_hash = file_hash("path/to/tribev2/best.ckpt")
export_prediction(model, "original.mp4", "predictions/video01-full.npz", atlas,
                  language="ta", text_weight=1.0, checkpoint_hash=checkpoint_hash)
export_prediction(model, "original.mp4", "predictions/video01-av.npz", atlas,
                  language="ta", text_weight=0.0, checkpoint_hash=checkpoint_hash)
```

NPZ contains original per-timestep/per-vertex predictions, ROI means, actual
segment starts and durations. Adjacent JSON contains original transcript words,
video/checkpoint hashes, ROI definition, modality setting and a configuration
signature. No brain images are required. Timings are TRIBE segment times; no extra
five-second correction is applied. Overlapping/gapped predictions are rejected
before summarization rather than counted twice. The current exporter expects a
single video timeline and at least 90% temporal coverage for each summarized clip.

## Calibration data (when available)

The user requested skipping collection now. To fit later, use 100–200 distinct
videos per language with two identified native speakers independently rating every
dimension. Use the same anchored scale (example below: 1–5) across languages.
Include strong/average/weak material and matched brand/audience/production quality;
winner-only sampling cannot establish fairness. Group repeated creators/campaigns,
edits, translated/dubbed variants and duplicate creatives under one `group_id`.
Byte-identical videos cannot count as independent examples. Native human ratings,
not Studio AI scores or raw views, are the targets.

Manifest example (one row shown; insufficient for training):

```json
{
  "unit": "video",
  "guideline_version": "brand-A-brief-v1",
  "dimensions": {
    "intro_energy": {"scale": [1,5], "target": [3,5], "guideline_id": "G1"},
    "brand_tone": {"scale": [1,5], "target": [4,5], "guideline_id": "G2"}
  },
  "native_raters": {"ta": ["native-rater-A", "native-rater-B"]},
  "samples": [{
    "id": "v01", "video_id": "v01", "group_id": "creator01-campaign01",
    "language": "ta", "prediction_file": "predictions/video01-full.npz",
    "ratings": {
      "intro_energy": {"native-rater-A": 3, "native-rater-B": 4},
      "brand_tone": {"native-rater-A": 4, "native-rater-B": 4}
    }
  }]
}
```

These numbers illustrate the schema, not actual collected ratings. Prediction
paths are relative to the manifest. Use `unit: "segment"` plus `start`/`end` and
native **segment ratings** for segment calibration. Whole-video labels cannot
validate scene-level flags. Keep every segment of the same video in the same group.
Each calibration is tied to a particular guideline version; ROI regression is not
a general semantic checker of arbitrary new product briefs.

```powershell
.\.venv\Scripts\python.exe -m tribe_calibration fit labeled_manifest.json calibration.json
```

This writes the model/evaluation JSON and a Markdown report. It requires at least
100 videos and 10 independent groups per language. The split targets exactly 20%
of videos; where group sizes make this impossible, it uses the closest feasible
split and reports the actual fraction. The held-out IDs are persisted. Five-fold
grouped cross-validation chooses ridge strength from 0.1, 1, 10, 100 **within the
training partition only**, refitting normalization inside each fold.

Per-language z-scores use the training reference mean/standard deviation only.
Never normalize against test/new submissions or force all languages to identical
ratings. Features are duration-weighted ROI means/variance and observed minimum,
maximum and absolute peak. Clip features use actual temporal overlap. Equal total
weight per video prevents a long video with many labeled clips dominating training.
All examples in a fit must use identical checkpoint, atlas and modality settings.

The report gives Pearson correlation, MAE/bias, within-one-point agreement with
the average of the raters and with each individual rater, inter-rater agreement,
training-mean baseline, worst errors, and language/dimension pairs below 80%.
The tolerance is one point on the **declared rating scale**, not one point out of
100. A high within-one rate alone is not sufficient; correlation can be undefined
on constant ratings. Inter-rater agreement is a practical reliability reference,
not a strict mathematical ceiling against averaged labels. Test-set size limits
precision. Do not repeatedly tune on this holdout or select an ablation using it
and then claim an independent final test.

## Diagnostic commands (require actual samples)

```powershell
.\.venv\Scripts\python.exe -m tribe_calibration diagnose matched.json raw_comparison.json
.\.venv\Scripts\python.exe -m tribe_calibration ablations ablations.json ablation_comparison.json
.\.venv\Scripts\python.exe -m tribe_calibration transcript-quality transcripts.json quality.json
```

`matched.json`: `samples` entries with `match_id`, `language` and `prediction_file`.
Use at least 10 English/regional matched pairs per regional language. Optional
`derived_score` and `thresholded_score` must come from the actual score-derivation
pipeline. Output includes per-ROI-summary differences and paired standardized
differences; it does not automatically infer causality or tone from amplitude.
Raw arrays retain per-timestep detail for inspection.

`ablations.json`: `samples` entries with `prediction_file`; every video needs full
and AV-only exports, optionally text weight 0.5. Checkpoint/atlas/time windows must
match. The report measures per-ROI mean absolute temporal change per second.
**Lower temporal variation is not evidence of better scores.** A constant model is
stable but useless. Scoring stability/accuracy needs labeled, separately calibrated
ablation evaluations; no winning configuration is declared automatically.

`transcripts.json`: `samples` entries with `video_id`, `language`,
`native_reviewer`, `reference_text` and `hypothesis_text`. At least 10 distinct
videos per language. Reports micro WER and CER plus individual errors, using NFC
Unicode normalization only. No translation, Romanization or English case folding.
Whitespace WER alone is insufficient for some scripts; CER and native review of
meaning, product names, omissions and code-switches are required.

## Segment flags and native approval

Use a calibration fitted to **segment** labels. `clips.json` is a list of
`{"start":0,"end":3}` entries. Boundaries are supplied by editors/shot detection;
TRIBE does not find semantic scenes. AV-only clips can additionally supply
`native_transcript` and `transcript_reviewer`, copied from original speech. Never
substitute an English translation.

`rules.json`:

```json
{
  "guideline_version": "brand-A-brief-v1",
  "rules": [{
    "guideline_id": "G1", "dimension": "intro_energy", "direction": "low",
    "language": "ta", "native_text": "",
    "english_explanation": "Energy is below the agreed intro range; tighten the opening line.",
    "native_reviewer": ""
  }]
}
```

Have a native editor author/approve the native-language template and fill their
identity; blank/unreviewed templates intentionally produce pending flags, not
machine-invented native copy. Supply separate low/high rules where applicable.
Each flag contains timestamps, dimension, calibrated value/target, original
transcript, native template and English explanation. A crossing is an editorial
flag, not a verified compliance violation. Context/lag limits precise localization.

```powershell
.\.venv\Scripts\python.exe -m tribe_calibration segments predictions/video01-full.npz segment_calibration.json clips.json rules.json internal_review.json
# A native speaker inspects each original span and suggestion before executing:
.\.venv\Scripts\python.exe -m tribe_calibration approve internal_review.json "clip-0:intro_energy" --reviewer "Native editor name" --language ta
.\.venv\Scripts\python.exe -m tribe_calibration creator-export internal_review.json creator_report.json
```

The export refuses missing or stale approval. Editing a signed suggestion,
transcript, timestamp, video or guideline version requires fresh approval. This
is a local attestation workflow, not identity verification. It does not send reports
to creators. These research reports are JSON/Markdown; Studio's existing PDF flow
is unchanged and is not a calibrated TRIBE PDF.

## Commercial use and current limitations

The TRIBE repository/weights use CC BY-NC 4.0. Company advertising/influencer
analysis raises a commercial-use concern; obtain appropriate permission/legal
clarification before deployment. This code does not claim such permission.

The neural inference path, real-language ASR quality, ROI atlas validity, GPU fit,
and human-rating agreement still require validation with real data/resources.
Synthetic regression tests verify software behavior only. No fabricated native
ratings, calibrated parameters, 80% pass list or commercial readiness is supplied.

Verification on 30 September 2026: the full 98-test suite passed before the final
two diagnostic tests were added; the final targeted run passed all 13 TRIBE tests
(87 existing tests plus 13 new tests covered across runs). Checks cover original
path/script preservation, transcription-only flags, cache isolation, text ablation,
ROI/time alignment, train-only normalization, grouped holdout, insufficient labels,
matched diagnostics, transcript error metrics, and native-approval export blocking.
Compilation and CLI help passed. Importing the calibration modules loaded none of
torch, transformers, faster_whisper or tribev2. All prediction/rating fixtures in
these tests are explicitly synthetic; they establish no real-language accuracy.
