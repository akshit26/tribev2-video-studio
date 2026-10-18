"""Separate, auditable creative-spread index; never a virality probability."""

from __future__ import annotations


LEVERS = (
    ("scroll_stop", "Stop the scroll", 25, (("hook", .7), ("visual", .3)),
     "Does the opening earn attention before viewers swipe?"),
    ("watch_through", "Hold attention", 25, (("structure", .45), ("visual", .3), ("voice", .25)),
     "Does the cut keep moving toward a payoff?"),
    ("payoff", "Deliver a payoff", 20, (("clarity", .6), ("credibility", .4)),
     "Is the promised benefit clear and supported?"),
    ("share_reason", "Reason to share", 15, (("emotion", .7), ("clarity", .3)),
     "Is there a specific, relatable idea worth passing on?"),
    ("response", "Prompt a response", 15, (("cta", .7), ("emotion", .3)),
     "Is there one easy action viewers can take?"),
)


def check_virality(review: dict) -> dict | None:
    """Reweight existing assessed evidence without another model call.

    The score is a comparative editing index. It deliberately does not use
    brand compliance, language name, historical views, or invented benchmarks.
    """
    if not review.get("available"):
        return None
    dimensions = {row["key"]: row for row in review.get("dimensions", [])}
    adjusted = {row["key"]: row for row in review.get("estimate", {}).get("dimensions", [])}
    needed = {key for _, _, _, components, _ in LEVERS for key, _ in components}
    if not needed.issubset(dimensions):
        return None
    levers = []
    for key, label, weight, components, question in LEVERS:
        component_scores = {part: max(0, min(100, float(adjusted.get(part, {}).get(
            "estimated_score", dimensions[part]["grade"] * 25)))) for part, _ in components}
        score = round(sum(component_scores[part] * factor for part, factor in components))
        bottleneck = min(components, key=lambda item: component_scores[item[0]])[0]
        ids = list(dict.fromkeys(source for part, _ in components
                                 for source in dimensions[part].get("source_ids", [])))[:6]
        levers.append({"key": key, "label": label, "score": score, "weight": weight,
                       "question": question, "bottleneck_key": bottleneck,
                       "bottleneck": dimensions[bottleneck]["label"], "source_ids": ids})
    score = round(sum(row["score"] * row["weight"] for row in levers) / 100)
    ranked = sorted(levers, key=lambda row: (row["score"], -row["weight"]))
    edits = review.get("edits", [])
    priorities = []
    for lever in ranked[:2]:
        related = next((edit for edit in edits if lever["bottleneck_key"] in edit.get("targets", [])), None)
        if related is None:
            related = next((edit for edit in edits if any(
                dimension in edit.get("targets", []) for dimension, _ in next(
                    components for key, _, _, components, _ in LEVERS if key == lever["key"]))), None)
        priorities.append({"lever": lever["label"], "score": lever["score"],
                           "bottleneck": lever["bottleneck"],
                           "edit": ({"start": related["start"], "end": related["end"],
                                     "instruction": related["instruction"]} if related else None)})
    return {"version": 1, "label": "Virality checker", "score": score,
            "scale": "0-100 creative-spread readiness index",
            "levers": levers, "priorities": priorities,
            "basis": "Five weighted combinations of existing evidence-adjusted creative grades. Brand compliance is excluded.",
            "note": "An editing diagnostic, not the chance of going viral, expected views, retention, shares or conversions. Validate against platform results."}
