"""Manual integration fixtures: synthetic public test text, never customer audio.

Run explicitly; this calls Google TTS to create three small speech fixtures.
Not included in unittest discovery and not part of production uploads.
"""
from pathlib import Path
import json
import subprocess
from gtts import gTTS
import imageio_ffmpeg

TEXTS = {
    "hi": "क्या आपकी पानी की बोतल बैग में लीक होती है? इस ढक्कन को बंद करके देखिए। खरीदने से पहले इसे पानी भरकर जांच लें। पूरी जानकारी के लिए कमेंट में लिंक लिखें।",
    "ta": "உங்கள் தண்ணீர் பாட்டில் பையில் கசிகிறதா? இந்த மூடியை நன்றாக மூடிப் பாருங்கள். வாங்குவதற்கு முன்பு தண்ணீர் நிரப்பி சோதனை செய்யுங்கள். மேலும் தகவலுக்கு கருத்தில் லிங்க் என்று எழுதுங்கள்.",
    "te": "మీ నీళ్ల సీసా బ్యాగులో లీక్ అవుతుందా? ఈ మూతను గట్టిగా మూసి చూడండి. కొనడానికి ముందు నీళ్లు నింపి పరీక్షించండి. పూర్తి వివరాల కోసం కామెంట్ లో లింక్ అని రాయండి.",
}

if __name__ == "__main__":
    for language, text in TEXTS.items():
        folder = Path("results/language_validation") / language
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "upload_info.json").write_text(json.dumps({"language": language, "platform": "general", "original_name": language + "_synthetic.mp4"}), encoding="utf-8")
        (folder / "expected.txt").write_text(text, encoding="utf-8")
        audio = folder / "sample.mp3"
        if not audio.exists():
            gTTS(text, lang=language).save(str(audio))
        subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=black:s=320x240:r=15",
                        "-i", str(audio), "-shortest", "-c:v", "libx264", "-threads", "2", "-c:a", "aac", str(folder / "input.mp4")], check=True)
        print(language + " synthetic audio ready", flush=True)
