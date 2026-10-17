# TRIBE language audit — findings before changing scoring

30 September 2026. This audit precedes the language-interface changes described in
TRIBE_CALIBRATION_GUIDE.md. No existing Studio scores were recalibrated.

## What is actually running

Studio uses Faster Whisper large-v3-turbo, BLIP and Qwen3-4B, not TRIBE predictions
(`studio_pipeline.py`, `studio_review.py`). It transcribes original audio; there is
no translation-to-English stage in this path. English explanations in a report
are not evidence of translated inference input. Historical English keyword rules
exist in `studio_scores.py`; these withhold unavailable regional-language scores.
The semantic score is derived from Qwen rubric grades. `studio_estimate.py` then
shrinks uncertain evidence toward an assumed neutral 50. That prior can cluster
uncertain reviews near 50, but is neither learned calibration nor proof that
TRIBE outputs are low. These are findings about this checkout, not an unseen
company pipeline.

## Concrete upstream language problems

Before this change, `ExtractWordsFromAudio` in `tribev2/eventstransforms.py`:

- Defaulted to `language="english"` and invoked WhisperX large-v3 with `--language en`.
- Accepted only English, French, Spanish, Dutch and Chinese. Hindi, Tamil and
  Telugu were rejected when requested directly.
- Did not expose language through `TribeModel.get_events_dataframe`.
- Did not explicitly request translation; forcing English transcription is a
  distinct problem. The command will now explicitly use `--task transcribe`.
- Reused `<audio>.tsv` independently of language, risking stale English transcripts.
- Passed a dangling `--align_model` option for non-English languages after removing
  an empty argument. Some WhisperX languages also lack a default alignment model.
- Rebuilt text through spaCy sentence processing; availability of language-specific
  parsers is another independent dependency, not proof of multilingual support.

The text encoder is Llama-3.2-3B (`tribev2/grids/defaults.py`). TRIBE itself is a
composition of pretrained encoders. Its original automatic transcription uses
WhisperX; "TRIBE only" here means its original feature pipeline plus a lightweight
calibrator, with no Qwen/BLIP creative judge, translation model or generated fixes.
Literal exclusion of every component model would preclude the stock text pathway.

## Text ablation and timing

`Data.get_loaders` removes extractors without matching events. The brain model's
`aggregate_features` inserts a zero tensor for a missing modality. Training config
also includes modality dropout. Hence dropping text events is supported by source
inspection; empirical stability and human agreement remain unmeasured. Scaling a
text projector's output is an explicitly experimental intermediate ablation.

`predict` returns segment objects alongside rows. Use their actual starts/durations,
not array indices as seconds. Training target offset is five seconds; the upstream
README says output is compensated for that lag. Do not subtract five seconds again.
Contextual and hemodynamic predictions do not provide frame-accurate causal tone
attribution. An atlas and verified vertex ordering are required for named ROIs;
auditory, visual or language activity is not itself a tone score.

## Diagnosis and measurements not available

No raw TRIBE prediction arrays or two-rater datasets were found in project results.
The local Hugging Face TRIBE cache contains config data but no downloaded brain
checkpoint; the TRIBE encoders are not in the inspected local model cache. Existing
Studio outputs cannot substitute for raw TRIBE predictions. The user confirmed
there are no matched videos/native ratings and instructed us to skip them.

Therefore the following are **not measured**, rather than failed or zero:

| Requested result | Status |
| --- | --- |
| Transcript quality on 10 real samples per language | Skipped: no reference transcripts/native ratings |
| Matched 10 English / 10 regional raw-ROI comparison | Skipped: no matched dataset or prediction arrays |
| Attribution to raw model, score derivation or English thresholds | Raw-TRIBE attribution unresolved; Studio's distinct score path identified above |
| Full vs weakened vs absent text stability | Source support verified; empirical comparison pending |
| 100–200 videos/language, two native raters | Skipped at user's request |
| Held-out correlation and +/-1 agreement | Unavailable; no fitted calibrations |
| Languages below 80% agreement | Unknown for every language, including English |

Normalization cannot recover information absent from TRIBE outputs. A z-score
aligns a reference distribution, not semantic meaning or rating quality. The
80–90% agreement goal is a hypothesis to test, not a deliverable we can certify
without labels. Report inter-rater agreement as a reference reliability level,
not a mathematically strict upper bound for agreement with averaged ratings.

## Resource and licensing constraints

The 3,068 MiB verification in STUDIO_GUIDE.md tested Qwen-based Studio, NOT full
TRIBE. A 3-billion-parameter text encoder alone needs roughly 6 GB in FP16 before
activations, the brain model and other encoders. This does not establish that
audio/video-only TRIBE fits either. Do not silently quantize/change encoders and
present that as an equivalent validated checkpoint. No full GPU run is claimed.

The repository and weights are CC BY-NC. Company influencer/ad scoring is a
commercial-use concern; obtain appropriate permission or legal clarification
before commercial deployment. No licensing exception is assumed.

Primary references:
- https://github.com/facebookresearch/tribev2 (model scope, timing and license)
- https://huggingface.co/facebook/tribev2 (released checkpoint/configuration)
- https://creativecommons.org/licenses/by-nc/4.0/ (noncommercial condition)

Code changes following this audit add an opt-in research workflow. They do not
claim to convert the existing Studio's saved reports into TRIBE evaluations.
