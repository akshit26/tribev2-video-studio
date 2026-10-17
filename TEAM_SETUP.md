# Team setup: local video report Studio

This project runs locally on **Windows 10/11, Python 3.11, and an NVIDIA GPU with at least 6 GB VRAM**. The tested laptop uses a GTX 1660 Ti. Other GPUs and drivers may need changes to the CUDA runtime. The Studio uses a 4 GB total GPU target, processes one video at a time, and stops a worker if its memory or temperature guard trips. A score is an editorial assessment, not a measured chance of virality.

Install [Git](https://git-scm.com/download/win), [Python 3.11](https://www.python.org/downloads/), a current [NVIDIA driver](https://www.nvidia.com/en-us/drivers/), and Microsoft Edge. Allow several gigabytes of free disk space for the Python environment and model downloads. The installer downloads model files from their public sources; no weights are stored in GitHub.

In PowerShell, clone the repository and run these commands **from its root**:

```powershell
git clone https://github.com/akshit26/tribev2-video-studio.git
cd tribev2-video-studio
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e ".[studio]" -c constraints-local.txt
.\.venv\Scripts\python.exe prepare_gpu.py
.\.venv\Scripts\python.exe prepare_review.py
.\.venv\Scripts\python.exe -m unittest discover -s tests -p 'test_studio*.py'
powershell -NoProfile -ExecutionPolicy Bypass -File .\start_studio.ps1
```

Open <http://127.0.0.1:8765>, upload an MP4/MOV or another supported video, and wait for the PDF download. Use `Stop Studio.cmd` to stop the service. Later starts require only `Start Studio.cmd`; the models remain in the local `cache/` folder. To start without opening a browser:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\start_studio.ps1 -NoBrowser
```

The `.env` file is optional for public model downloads. If your Hugging Face access requires a personal token, copy `.env.example` to `.env`, replace its placeholder with **your own** read token, and keep `.env` local. Never paste a token into an issue or commit. Uploaded videos, reports, model weights, and `.env` are excluded from Git.

Reports use Edge to render Indian scripts into the PDF. If a machine fails setup, save the terminal output and the relevant `results/studio/<job-id>/worker_*.log` file without sharing customer videos or tokens. The full usage and limitations are in [STUDIO_GUIDE.md](STUDIO_GUIDE.md).
