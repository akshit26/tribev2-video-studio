<div align="center">

# TRIBE v2

**A Foundation Model of Vision, Audition, and Language for In-Silico Neuroscience**

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/facebookresearch/tribev2/blob/main/tribe_demo.ipynb)
[![License: CC BY-NC 4.0](https://img.shields.io/badge/License-CC%20BY--NC%204.0-lightgrey.svg)](https://creativecommons.org/licenses/by-nc/4.0/)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)

📄 [Paper](https://arxiv.org/abs/2605.04326)  |  ▶️ [Demo](https://aidemos.atmeta.com/tribev2/) | 🤗 [Weights](https://huggingface.co/facebook/tribev2)

</div>

TRIBE v2 is a deep multimodal brain encoding model that predicts fMRI brain responses to naturalistic stimuli (video, audio, text). It combines state-of-the-art text, audio and video models into a unified Transformer architecture that maps multimodal representations onto the cortical surface.

## Local video report studio

Double-click `Start Studio.cmd` for the local upload interface, numeric hook/CTA/creative-review scores, emotional-language values, and downloadable PDF reports. See [STUDIO_GUIDE.md](STUDIO_GUIDE.md). The compact Studio profile uses sequential GPU models and an automatic maximum GPU target (5.5 GiB on the tested 6 GiB GPU, with desktop and worker reserves); it does not run full TRIBE fMRI inference or predict audience outcomes.

Install the recommended free local writer once with `.venv\Scripts\python.exe prepare_writer.py`. Model weights and generated drafts stay outside Git.

Open **Script Writer** inside Studio to generate hook options and spoken scripts using an attributed writing/research library. It revises toward an 80/100 script editorial target with bounded attempts, saved critique history, manual editing, natural-language change requests with live previews, paragraph revisions and text/print-to-PDF exports. Niche-matched creator examples support natural English, Hindi and Hinglish scripts; optional Kumo estimates use imported real post outcomes. Choose NVIDIA Nemotron 3 Ultra for hosted content writing (set server-side `NVIDIA_API_KEY`), or use the free local engine. Script readiness is separate from finished-video scoring and TRIBE inference; see the [Script Writer guide](STUDIO_GUIDE.md#script-writer).

For a fresh Windows machine, follow [TEAM_SETUP.md](TEAM_SETUP.md) before starting Studio. Model weights, uploaded videos, local reports, and Hugging Face credentials are downloaded or created on each machine and are not included in this repository.

For the separate original-language TRIBE research path, see the
[language audit](TRIBE_LANGUAGE_AUDIT.md) and [calibration workflow](TRIBE_CALIBRATION_GUIDE.md).
It supports text-stream ablations and lightweight native-rating calibration without
translation. No real-language accuracy or full-TRIBE 4 GB GPU fit is claimed;
calibration requires labeled data and a verified ROI mapping.

## Quick start

Load a pretrained model from HuggingFace and predict brain responses to a video:

```python
from tribev2 import TribeModel

model = TribeModel.from_pretrained("facebook/tribev2", cache_folder="./cache")

df = model.get_events_dataframe(video_path="path/to/video.mp4")
preds, segments = model.predict(events=df)
print(preds.shape)  # (n_timesteps, n_vertices)
```

Predictions are for the "average" subject (see paper for details) and live on the **fsaverage5** cortical mesh (~20k vertices).
They are offset by 5 seconds in the past, in order to compensate for the hemodynamic lag.

You can also pass `text_path` or `audio_path` to `model.get_events_dataframe` — text is automatically converted to speech and transcribed to obtain word-level timings.

For a full walkthrough with brain visualizations, see the [Colab demo notebook](https://colab.research.google.com/github/facebookresearch/tribev2/blob/main/tribe_demo.ipynb).

## Installation

**Basic** (inference only):
```bash
pip install -e .
```

**With brain visualization**:
```bash
pip install -e ".[plotting]"
```

**With training dependencies** (PyTorch Lightning, W&B, etc.):
```bash
pip install -e ".[training]"
```

## Training a model from scratch

### 1. Set environment variables

Configure data/output paths and Slurm partition (or edit `tribev2/grids/defaults.py` directly):

```bash
export DATAPATH="/path/to/studies"
export SAVEPATH="/path/to/output"
```


### 2. Run training

**Local test run:**
```bash
python -m tribev2.grids.test_run
```

**Grid search on Slurm:**
```bash
python -m tribev2.grids.run_cortical
python -m tribev2.grids.run_subcortical
```

## Project structure

```
tribev2/
├── main.py              # Experiment pipeline: Data, TribeExperiment
├── model.py             # FmriEncoder: Transformer-based multimodal→fMRI model
├── pl_module.py         # PyTorch Lightning training module
├── demo_utils.py        # TribeModel and helpers for inference from text/audio/video
├── eventstransforms.py  # Custom event transforms (word extraction, chunking, …)
├── utils.py             # Multi-study loading, splitting, subject weighting
├── utils_fmri.py        # Surface projection (MNI / fsaverage) and ROI analysis
├── grids/
│   ├── defaults.py      # Full default experiment configuration
│   └── test_run.py      # Quick local test entry point
├── plotting/            # Brain visualization (PyVista & Nilearn backends)
└── studies/             # Dataset definitions (Algonauts2025, Lahner2024, …)
```

## Contributing to open science

If you use this software, please share your results with the broader research community using the following citation:

```bibtex
@article{dascoli2026foundation,
  title={A foundation model of vision, audition, and language for in-silico neuroscience},
  author={d'Ascoli, St{\'e}phane and Rapin, J{\'e}r{\'e}my and Benchetrit, Yohann and Brooks, Teon and Begany, Katelyn and Raugel, Jos{\'e}phine and Banville, Hubert and King, Jean-R{\'e}mi},
  journal={arXiv preprint arXiv:2605.04326},
  year={2026}
}
```

## License

This project is licensed under CC-BY-NC-4.0. See [LICENSE](LICENSE) for details.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for how to get involved.


Script video learning now defaults to actual short-video research: YouTube Shorts candidates first, TikTok second, Instagram third. Supply direct links or upload up to three 5?180 second clips when public discovery is restricted. Whisper transcribes original speech locally; Muse receives those transcripts and book principles, derives timestamped conditional mechanisms, and saves rules for matching niches and languages. This is persistent retrieval memory, not weight fine-tuning or script-template training. View counts are observed snapshots within accessible candidates, not global viral rankings or causal evidence. Hindi and English speech are filtered by detected language; ASR remains unverified by a native reviewer.

Select **GPT-OSS drafts + Gemma review** with server-side `GPT_OSS_API_KEY` and `GEMMA_API_KEY`. GPT-OSS 20B drafts; Gemma 4 31B reviews and edits spoken words. Muse uses `MUSE_API_KEY`. Hosted availability and account limits apply; local generation remains available. Keys stay in the ignored `.env`.

Kumo is attempted on the final team draft only when real comparable post outcomes meet the existing data requirements. It never invents labels from public views. Editorial readiness is separate from genuine TRIBE inference: recorded-media rating requires authentic `tribe_prediction.npz` and matching `.json` exports in the original video job, plus a fitted `TRIBE_CALIBRATION_ARTIFACT`. POST `/api/scripts/{id}/tribe-score` with `video_job_id` to apply that calibration. TRIBE has no native 0?100 script virality scale; missing predictions or calibration produce an explicit unavailable state. See TRIBE_CALIBRATION_GUIDE.md.


The current writer produces one JSON field: `final_script`. New scripts target 30 seconds and open with a statement of fewer than 12 words. The entire script appears in one expanding text area, with optional short inline bracketed cues. Copy, manual edits, full-script change requests, text export and print export all use this field. Archived scene-based drafts are flattened when opened. The new generation path makes one validated script request instead of scene generation, scene repairs, a separate voice edit and automatic editorial scoring; no 80+ score is invented. Kumo remains optional. GPT-OSS configuration now requires only GPT_OSS_API_KEY. NVIDIA team calls allow 180 seconds, with a matching overall deadline and no automatic transport retries.
