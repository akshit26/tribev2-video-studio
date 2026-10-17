"""Model-free language controls for the stock TRIBE transcription dependency."""
import re
from pathlib import Path

LANGUAGES = dict(english="en", french="fr", spanish="es", dutch="nl", chinese="zh",
                hindi="hi", tamil="ta", telugu="te", bengali="bn", marathi="mr",
                gujarati="gu", kannada="kn", malayalam="ml", punjabi="pa",
                urdu="ur", assamese="as", nepali="ne", sanskrit="sa", sindhi="sd",
                odia="or", oriya="or")


def language_code(language):
    value = (language or "auto").strip().lower()
    value = LANGUAGES.get(value, value)
    if value != "auto" and not re.fullmatch(r"[a-z]{2,3}", value):
        raise ValueError("Use a language code such as hi, ta or te, or auto.")
    return value


def transcript_cache_path(audio, language):
    # Both language and source revision affect the cache; never reuse legacy
    # English-only .tsv files. Language-code acceptance is not ASR support.
    audio = Path(audio)
    stat = audio.stat()
    return audio.with_name(f"{audio.stem}.tribe-transcribe-v2-{language_code(language)}-{stat.st_size}-{stat.st_mtime_ns}.tsv")


def whisperx_command(audio, output, language, device, compute_type):
    code = language_code(language)
    cmd = ["uvx", "whisperx", str(audio), "--model", "large-v3",
           "--task", "transcribe", "--device", device, "--compute_type", compute_type,
           "--batch_size", "1", "--output_dir", str(output), "--output_format", "json"]
    if code != "auto":
        cmd += ["--language", code]
    if code == "en":
        cmd += ["--align_model", "WAV2VEC2_ASR_LARGE_LV60K_960H"]
    return cmd
