# NVIDIA Whisper Large V3 — prepared for future use

The project virtual environment has `nvidia-riva-client` installed. The official
[Riva Python clients](https://github.com/nvidia-riva/python-clients) are cloned in
ignored `cache/riva/python-clients`. Your supplied key is stored only in ignored
`.env` as `RIVA_API_KEY`.

Verify readiness without sending audio or making a hosted request:

```powershell
.venv/Scripts/python.exe prepare_riva.py --check
```

When you choose to use it, prepare mono 16-bit PCM WAV audio, then run:

```powershell
.venv/Scripts/python.exe prepare_riva.py --input-file audio.wav --language-code hi
```

Use `en` for English or `multi` for automatic language detection. The helper uses
TLS to `grpc.nvcf.nvidia.com:443`, function ID
`b702f636-f60c-4a3d-a6f4-f3568c13bd7d`, and a 180-second deadline. No key is placed
in process arguments. Hosted access depends on the NVIDIA account. No model
weights were downloaded and no audio has been sent during setup. The writer and
existing research workflow do not invoke this helper automatically.
