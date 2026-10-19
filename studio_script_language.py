"""Spoken register, writing system and approximate timing for creator scripts."""
import math
import re

PROFILES = {
    "English": {"min_wps":2, "target_wps":2.4, "max_wps":3, "script":"latin",
        "direction":"Everyday spoken English. Use contractions and concrete observations. Write like a voice note to one friend, not a polished brand manifesto."},
    "Hindi": {"min_wps":1.8, "target_wps":2.2, "max_wps":2.8, "script":"devanagari",
        "direction":"Natural conversational Hindi in Devanagari, as spoken to a friend. Use correct postpositions, agreement and idiomatic word order. Do not add यार or मतलब just to sound casual, repeat वही/फिर भी, or end every thought with a filler. No textbook translation, Sanskrit-heavy advertising, forced rhymes or English sentences translated word for word. Brand names and common product terms may stay English."},
    "Hindi (Roman)": {"min_wps":1.8, "target_wps":2.2, "max_wps":2.8, "script":"latin",
        "direction":"Conversational Hindi written in Roman letters: mujhe, tum, matlab, bas, hai. Keep Hindi sentence structure; brand and familiar product terms may remain English. No Devanagari or stiff literal translation."},
    "Hinglish": {"min_wps":2, "target_wps":2.4, "max_wps":3, "script":"latin",
        "direction":"Natural Roman-script Hindi-English code-switching, like an Indian creator's voice note. Hindi grammar with familiar English product words, or a natural switch at a clause. Do not alternate languages mechanically, add a translated duplicate, or write entirely English. No caricature accents or forced slang."},
}
ALIASES = {"en":"English","english":"English","hi":"Hindi","hindi":"Hindi","हिंदी":"Hindi",
           "हिन्दी":"Hindi","hindi (devanagari)":"Hindi","roman hindi":"Hindi (Roman)",
           "hindi (roman)":"Hindi (Roman)","hinglish":"Hinglish","hinglish (roman)":"Hinglish"}


def normalize_language(value):
    return ALIASES.get(value.strip().casefold(), value.strip())


def profile(brief):
    return PROFILES.get(normalize_language(brief.get("language", "English")))


def word_budget(brief):
    p = profile(brief) or PROFILES["English"]
    seconds = brief["duration"]
    return math.floor(seconds*p["min_wps"]), round(seconds*p["target_wps"]), math.floor(seconds*p["max_wps"])


def guidance(brief):
    p = profile(brief)
    return "LANGUAGE / REGISTER: " + (p["direction"] if p else "Write naturally in " + brief.get("language", "English")) + " Draft directly in this language; do not translate an English ad. "


def language_issues(spoken, brief):
    p = profile(brief)
    if not p:
        return []
    letters = [c for c in spoken if c.isalpha()]
    if not letters:
        return []
    ratio = sum('\u0900' <= c <= '\u097f' for c in letters)/len(letters)
    name = normalize_language(brief.get("language", "English"))
    if p["script"] == "devanagari" and ratio < .5:
        return ["Requested Hindi in Devanagari, but most speech uses another writing system. Rewrite in conversational Hindi."]
    if p["script"] == "latin" and ratio > .1:
        return [f"Requested {name} in Roman letters. Rewrite spoken lines in the selected writing system."]
    if name in {"Hinglish", "Hindi (Roman)"} and len(spoken.split()) >= 20:
        markers = set(re.findall(r"\b(?:hai|hain|ho|tha|thi|toh|aur|nahi|nahin|matlab|yaar|mujhe|tum|bas|kya|ka|ki|ke|mera|meri|yeh|ye|woh|bhi|mein|se|kar|liye|kyun|haan|abhi)\b", spoken.casefold()))
        if len(markers) < 2:
            return [f"Requested {name}, but speech appears entirely English. Use natural Hindi phrasing, not token slang."]
    return []


AI_PHRASES = ("silent vow", "invisible armor", "invisible armour", "daily plot twist", "auditioning my", "unlock your glow", "unlock the secret", "game-changing", "game changer", "revolutionize your", "elevate your routine", "say hello to", "say goodbye to", "meet your new", "your skin will thank you", "your face will thank you", "for good measure today", "today right now", "स्किन को कहें अलविदा", "निखार का जादू", "क्रांतिकारी समाधान")


def naturalness_issues(spoken, brief):
    if brief.get("content_mode", "organic") == "paid_ad":
        return []
    found = [phrase for phrase in AI_PHRASES if phrase in spoken.casefold()]
    return ["Generic or over-written ad phrasing: " + ", ".join(found[:3]) + ". Replace with a specific everyday observation in the creator's own words."] if found else []
