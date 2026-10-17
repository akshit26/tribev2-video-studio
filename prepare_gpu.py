"""Install the project's pinned Windows CUDA wheels and compact vision model."""
from __future__ import annotations

import concurrent.futures
import hashlib
from pathlib import Path
import subprocess
import sys
import time
import urllib.request

ROOT = Path(__file__).resolve().parent


def fetch_verified(url: str, target: Path, sha256: str | None = None):
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        with target.open("rb") as stream:
            valid = sha256 is None or hashlib.file_digest(stream, "sha256").hexdigest() == sha256
        if valid:
            print(f"Already available: {target.name}", flush=True)
            return
    req = urllib.request.Request(url + "?range_probe=1", headers={"Range": "bytes=0-0"})
    with urllib.request.urlopen(req, timeout=45) as response:
        content_range = response.headers.get("Content-Range", "")
        if not content_range:
            data = response.read()
            if sha256 and hashlib.sha256(data).hexdigest() != sha256:
                raise ValueError("Download checksum mismatch")
            target.write_bytes(data)
            return
        total = int(content_range.split("/")[-1])
        response.read()
    step = 4 * 1024 * 1024
    print(f"Downloading {target.name}: {total / 1024**2:.0f} MiB", flush=True)

    def part(start):
        end = min(start + step, total) - 1
        for attempt in range(4):
            try:
                req = urllib.request.Request(url + f"?range_part={start}", headers={"Range": f"bytes={start}-{end}"})
                with urllib.request.urlopen(req, timeout=60) as response:
                    actual = response.headers.get("Content-Range", "")
                    data = response.read()
                if not actual.startswith(f"bytes {start}-{end}/") or len(data) != end - start + 1:
                    raise ValueError("Unexpected download range")
                return start, data
            except Exception:
                if attempt == 3:
                    raise
                time.sleep(1 + attempt)

    temporary = target.with_suffix(target.suffix + ".partial")
    with temporary.open("wb") as stream, concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        stream.truncate(total)
        starts = iter(range(0, total, step))
        pending = {pool.submit(part, start) for start in [next(starts, None) for _ in range(8)] if start is not None}
        finished, last = 0, -1
        while pending:
            completed, pending = concurrent.futures.wait(pending, return_when=concurrent.futures.FIRST_COMPLETED)
            for future in completed:
                start, data = future.result()
                stream.seek(start)
                stream.write(data)
                finished += len(data)
                percent = int(finished / total * 10) * 10
                if percent != last:
                    print(f"{target.name}: {percent}%", flush=True)
                    last = percent
                following = next(starts, None)
                if following is not None:
                    pending.add(pool.submit(part, following))
    with temporary.open("rb") as stream:
        if sha256 and hashlib.file_digest(stream, "sha256").hexdigest() != sha256:
            raise ValueError(f"Checksum mismatch: {target.name}")
    temporary.replace(target)


def main():
    if sys.platform != "win32" or sys.version_info[:2] != (3, 11):
        raise SystemExit("This installer targets Windows / Python 3.11; use official PyTorch wheels on other systems.")
    wheels = [
        ("torch-2.6.0%2Bcu124-cp311-cp311-win_amd64.whl", "6a1fb2714e9323f11edb6e8abf7aad5f79e45ad25c081cde87681a18d99c29eb"),
        ("torchvision-0.21.0%2Bcu124-cp311-cp311-win_amd64.whl", "000a013584ad2304ab30496318145f284ac364622addb5ee3a5abd2769ba146f"),
        ("torchaudio-2.6.0%2Bcu124-cp311-cp311-win_amd64.whl", "a25e146ce66ea9a6aed39008cc2001891bdf75253af479a4c32096678b2073b3"),
    ]
    paths = []
    for filename, checksum in wheels:
        target = ROOT / "cache" / "setup" / filename.replace("%2B", "+")
        fetch_verified("https://download.pytorch.org/whl/cu124/" + filename, target, checksum)
        paths.append(str(target))
    subprocess.run([sys.executable, "-m", "pip", "install", "--no-deps", *paths], check=True)
    folder = ROOT / "cache" / "blip-image-captioning-base"
    base = "https://huggingface.co/Salesforce/blip-image-captioning-base/resolve/main/"
    for name in ["config.json", "preprocessor_config.json", "special_tokens_map.json", "tokenizer.json", "tokenizer_config.json", "vocab.txt"]:
        fetch_verified(base + name, folder / name)
    fetch_verified(base + "pytorch_model.bin", folder / "pytorch_model.bin", "d6638651a5526cc2ede56f2b5104d6851b0755816d220e5e046870430180c767")
    folder = ROOT / "cache" / "emotion-english-distilroberta-base"
    base = "https://huggingface.co/j-hartmann/emotion-english-distilroberta-base/resolve/main/"
    for name in ["config.json", "merges.txt", "special_tokens_map.json", "tokenizer.json", "tokenizer_config.json", "vocab.json"]:
        fetch_verified(base + name, folder / name)
    fetch_verified(base + "pytorch_model.bin", folder / "pytorch_model.bin", "dde1eadd81741344dd707d1c482a3293810eb895c873053213ccdb2b57ca9e95")
    print("CUDA wheels and compact vision/emotion models are ready. Faster Whisper downloads on first use if not cached.", flush=True)


if __name__ == "__main__":
    main()
