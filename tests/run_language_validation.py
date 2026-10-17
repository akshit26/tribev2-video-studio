"""Manual sequential GPU smoke test on synthetic, non-customer speech fixtures."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from studio_pipeline import _run_worker, _write_json

if __name__ == "__main__":
    results = []
    for language in sys.argv[1:] or ("te", "ta", "hi"):
        output = ROOT / "results/language_validation_turbo" / language
        ok, peak, reason = _run_worker("speech", output / "input.mp4", output, "cuda", 4096,
                                       lambda *_: None, 0, 100)
        row = {"language": language, "ok": ok, "peak_gpu_mb": peak, "reason": reason}
        if ok:
            transcript = json.loads((output / "transcript.json").read_text(encoding="utf-8"))
            row["text"] = " ".join(s["text"] for s in transcript["segments"])
        results.append(row)
        _write_json(ROOT / "results/language_validation_turbo/results.json", results)
        print(json.dumps(row, ensure_ascii=True), flush=True)
