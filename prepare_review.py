"""Download checksum-verified local multilingual review models and CUDA runtime."""
from pathlib import Path
import concurrent.futures
import hashlib
import urllib.request
import zipfile

from prepare_gpu import fetch_verified, ROOT


def runtime():
    name = "llama-b11226-bin-win-cuda-12.4-x64.zip"
    target = ROOT / "cache" / "setup" / name
    digest = "f120cc7105fccada76ad3ee3a40871dbcfb174221f7e279b7fb25d1850c90b1a"
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        with urllib.request.urlopen("https://github.com/ggml-org/llama.cpp/releases/download/b11226/" + name, timeout=60) as source, target.open("wb") as dest:
            while chunk := source.read(1024 * 1024):
                dest.write(chunk)
    with target.open("rb") as stream:
        if hashlib.file_digest(stream, "sha256").hexdigest() != digest:
            raise ValueError("llama.cpp runtime checksum mismatch")
    directory = (ROOT / "cache" / "llama").resolve()
    with zipfile.ZipFile(target) as archive:
        for item in archive.infolist():
            if not (directory / item.filename).resolve().is_relative_to(directory):
                raise ValueError("Unsafe archive path")
        archive.extractall(directory)
    print("CUDA review runtime ready", flush=True)


def speech():
    folder = ROOT / "cache" / "faster-whisper-large-v3-turbo"
    base = "https://huggingface.co/dropbox-dash/faster-whisper-large-v3-turbo/resolve/main/"
    for name in ["config.json", "tokenizer.json", "vocabulary.json", "preprocessor_config.json"]:
        fetch_verified(base + name, folder / name)
    fetch_verified(base + "model.bin", folder / "model.bin", "e76620f83d5f5b69efd3d87e3dc180c1bd21df9fbebacfd4335e5e1efcc018da")


def review():
    name = "Qwen3-4B-Instruct-2507-Q4_K_M.gguf"
    fetch_verified("https://huggingface.co/unsloth/Qwen3-4B-Instruct-2507-GGUF/resolve/main/" + name,
                   ROOT / "cache" / "review" / name, "3605803b982cb64aead44f6c1b2ae36e3acdb41d8e46c8a94c6533bc4c67e597")


if __name__ == "__main__":
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        for task in [pool.submit(runtime), pool.submit(speech), pool.submit(review)]:
            task.result()
    print("Multilingual review models ready", flush=True)
