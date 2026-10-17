# Analyze your video

For the current GPU upload interface, creative scorecard, and PDF downloads, use **[STUDIO_GUIDE.md](STUDIO_GUIDE.md)** or double-click **Start Studio.cmd**. The original scientific TRIBE runner below is separate from the compact creative-report app.

The project root is `C:\Users\Asus\Downloads\tribev2-main\tribev2-main`.
Your original working folder was its `tribev2` package subfolder. Run the commands below from the project root.

## What is configured

Current setup: CUDA PyTorch 2.6.0+cu124 is installed and the compact Studio pipeline has been tested on the GTX 1660 Ti. The original TRIBE published config and event preprocessing were validated, but full fMRI inference has not run. The Studio produces creative-review indices and language-tone values using compact models; see STUDIO_GUIDE.md.

- `.venv` is an isolated Python 3.11 environment. Your system Python is unchanged.
- `.env` contains your Hugging Face token. The runner loads it automatically, and `.gitignore` excludes it. Do not share this file. Replace the token that was pasted into chat at <https://huggingface.co/settings/tokens>, then update `.env` locally.
- The supplied token was verified for TRIBE and `meta-llama/Llama-3.2-3B`. A replacement token also needs access to that gated model.
- Fixes in `demo_utils.py` preserve Hub IDs on Windows, read the released YAML path/tuple tags safely, use the downloaded checkpoint path, and apply the selected device to feature extractors. CPU WhisperX now uses int8 instead of float16.

## Run it

Open PowerShell:

```powershell
cd "C:\Users\Asus\Downloads\tribev2-main\tribev2-main"
$video = "C:\Users\Asus\Downloads\WhatsApp Video 2026-09-26 at 5.30.16 PM (1).mp4"
```

Video measurements and sampled frames, with no AI weight downloads:

```powershell
.\.venv\Scripts\python.exe .\analyze_video.py $video --inspect-only
Start-Process .\results\my_video\video_report.html
```

Add an automatic timed speech transcript:

```powershell
.\.venv\Scripts\python.exe .\analyze_video.py $video --transcribe-only
```

Attempt full TRIBE predictions with reduced text-encoder memory:

```powershell
.\.venv\Scripts\python.exe .\analyze_video.py $video --low-memory
```

`--low-memory` uses the existing text extractor's float16/CPU-offload mode. Video and brain model architectures are unchanged. It does not guarantee that all models fit on a 6 GB GPU. Downloads and feature extraction can be substantial. `--device cpu` moves the main model and feature extractors to CPU; CPU inference can be very slow and still requires substantial RAM. Avoid combining `--low-memory` and `--device cpu` when you need strictly CPU-only execution: Accelerate chooses devices itself.

By default, the runner uses Faster Whisper `small` on CPU for word timestamps, then passes those words through the TRIBE event-processing pipeline. This is a practical alternative to the original WhisperX `large-v3` forced-alignment pipeline, so predictions may differ due to transcription/timing differences. Use `--speech-model medium` for a larger speech model, or `--whisperx` to run the original pipeline (requires `uvx` and FFmpeg on PATH). The original pipeline assumes English; the alternate pipeline detects language and currently maps English, French, Spanish, Dutch, and Chinese into TRIBE's text processing.

Use `--output .\results\another_video` to keep different videos' outputs separate. Transcripts are cached by input path, size, modification time, and speech-model choice. Check automatically generated words and product names before relying on them.

## Outputs

| File | Meaning |
|---|---|
| `video_report.html` | Local report with metadata and 12 sampled frames |
| `video_info.json` | Duration, dimensions, frame rate, file size, and audio presence |
| `video_metrics.csv` | Per-second brightness, sampled visual change, audio RMS and peak dBFS |
| `transcript.txt`, `transcript.json` | Automatic speech and word timestamps after transcription succeeds |
| `subtitles.srt` | Editable automatically timed subtitles |
| `events.csv` | Processed video/audio/word events after TRIBE preprocessing succeeds |
| `brain_predictions.npy` | Full time × cortical-vertex prediction array after inference succeeds |
| `brain_timeline.csv` | Segment timing and descriptive brain-output statistics |
| `brain_info.json` | Model, output shape, timing and interpretation notes |
| `brain_timeline.png`, `brain_heatmap.png` | Plots of model output after inference succeeds |

Read the array with `numpy.load("results/my_video/brain_predictions.npy")`. Rows align with `brain_timeline.csv`. The official `tribe_demo.ipynb` also shows how to plot outputs on a cortical surface.

## What the results mean

TRIBE predicts average-subject fMRI-like cortical responses, not this presenter's or any particular viewer's brain activity. Its outputs are not validated emotion, attention, purchase-intent, retention, or virality scores. You cannot calculate prediction accuracy or brain correlations without measured fMRI ground truth. Video measurements and editorial observations are separate from model predictions.

The upstream README describes predictions as shifted five seconds into the past to account for hemodynamic lag. This runner saves the actual model segment times and does not apply an additional shift.

## Reinstall on another machine

For a hosted GPU, open `Analyze_in_Colab.ipynb` in Google Colab, select a GPU runtime, and follow its cells. Upload `tribe_video_source.zip`, then enter a replacement token in the hidden prompt and upload your video. This notebook has not been executed in Colab. The source archive excludes credentials, model downloads, and your video. The video is uploaded to Colab only when you select it yourself. If GPU memory runs out, select a runtime with more GPU memory; this laptop has only 6 GB.

Use Python 3.11 and run from this project root:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[analysis,plotting,training]" -c constraints-local.txt
```

For a compatible NVIDIA setup, install matching CUDA builds of torch, torchvision, and torchaudio using the PyTorch installer instructions: <https://pytorch.org/get-started/locally/>. The repository requires torch 2.5/2.6, torchvision 0.20/0.21, and the matching torchaudio version. Check the installed build:

```powershell
.\.venv\Scripts\python.exe -c "import torch; print(torch.__version__, torch.cuda.is_available())"
```

The constraints prevent the old neuralset package from resolving to an obsolete Transformers build or incompatible major Hub/pandas versions. Keep `faster-whisper` and `accelerate` installed for this runner.

Regression checks (no model downloads):

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Official references: [TRIBE model card](https://huggingface.co/facebook/tribev2), [upstream code and notebook](https://github.com/facebookresearch/tribev2), [HF token configuration](https://huggingface.co/docs/huggingface_hub/package_reference/environment_variables).
