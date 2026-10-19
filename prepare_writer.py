"""Install the pinned, checksum-verified free local script-writing model."""
from prepare_gpu import ROOT, fetch_verified

REPOSITORY = "unsloth/Qwen3.5-4B-GGUF"
REVISION = "e87f176479d0855a907a41277aca2f8ee7a09523"
FILENAME = "Qwen3.5-4B-Q4_K_M.gguf"
SHA256 = "00fe7986ff5f6b463e62455821146049db6f9313603938a70800d1fb69ef11a4"
TARGET = ROOT / "cache" / "writer" / FILENAME


if __name__ == "__main__":
    fetch_verified(f"https://huggingface.co/{REPOSITORY}/resolve/{REVISION}/{FILENAME}", TARGET, SHA256)
    print("Local Qwen3.5 writer installed and checksum verified. No hosted inference credits required.", flush=True)
