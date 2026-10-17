"""Transparent viewer-response hypotheses derived from existing creative grades.

These are editorial mechanisms, not brain measurements or outcome predictions.
"""

MECHANISMS = (
    ("attention", "Attention", ("hook", "structure", "visual"),
     "The opening and changing visual rhythm give a reason to keep watching."),
    ("comprehension", "Comprehension", ("clarity", "structure", "visual"),
     "The message and pictures make the product payoff easy to follow."),
    ("trust", "Trust", ("credibility", "visual", "voice"),
     "Demonstration, claims and delivery support belief in the message."),
    ("motivation", "Action motivation", ("emotion", "clarity", "cta"),
     "The audience stake, promised payoff and next step support action."),
)


def viewer_response_map(dimensions):
    """Summarize rubric evidence without inventing new independent ratings."""
    rows = {row.get("key"): row for row in dimensions}
    mapped = []
    for key, label, components, meaning in MECHANISMS:
        available = [rows[name] for name in components if name in rows]
        if not available:
            continue
        # The weakest relevant component is useful for editing. The map does
        # not feed back into the overall score and double-count those grades.
        weakest = min(available, key=lambda row: row["grade"])
        ids = list(dict.fromkeys(source for row in available for source in row.get("source_ids", [])))[:6]
        mapped.append({"key": key, "label": label, "status": (
            "Needs work" if weakest["grade"] < 2 else
            "Mixed" if weakest["grade"] < 3 else "Supported"),
            "bottleneck": weakest["label"], "bottleneck_grade": weakest["grade"],
            "meaning": meaning, "source_ids": ids,
            "basis": list(components),
            "note": "Editorial hypothesis from the listed creative grades; no brain or audience response was measured."})
    return mapped
