"""Free local writer models; video review keeps its separate model."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LOCAL_MODELS = {
    "qwen35": ("Qwen3.5 4B - local writer", ROOT / "cache/writer/Qwen3.5-4B-Q4_K_M.gguf"),
    "qwen3": ("Qwen3 4B - compatibility model", ROOT / "cache/review/Qwen3-4B-Instruct-2507-Q4_K_M.gguf"),
}


def resolve_local_model(brief):
    choice = brief.get("local_model", "auto")
    if choice == "auto":
        choice = "qwen35" if LOCAL_MODELS["qwen35"][1].exists() else "qwen3"
    if choice not in LOCAL_MODELS:
        raise ValueError("Choose auto, qwen35 or qwen3 local writer model.")
    name, path = LOCAL_MODELS[choice]
    if not path.exists():
        raise ValueError("Local writer model is missing. Run prepare_writer.py for Qwen3.5 or prepare_review.py for the compatibility model.")
    return choice, name, path


def local_configuration():
    return [{"id": key, "name": name, "installed": path.exists()} for key, (name, path) in LOCAL_MODELS.items()]
