"""Small per-language ridge models with grouped, leakage-free evaluation."""
import hashlib
import json
import math
from pathlib import Path

import numpy as np


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def roi_series(predictions, atlas):
    values = np.asarray(predictions, dtype=float)
    if values.ndim != 2 or not values.size or not np.isfinite(values).all():
        raise ValueError("Predictions must be a finite time-by-vertex matrix")
    if atlas.get("vertex_count") != values.shape[1] or not atlas.get("vertex_order") or not atlas.get("provenance"):
        raise ValueError("Atlas must document matching vertex_count, vertex_order and provenance")
    names, arrays = [], []
    for name, indices in sorted(atlas.get("rois", {}).items()):
        idx = np.asarray(indices)
        if idx.ndim != 1 or not len(idx) or idx.dtype.kind not in "iu" or len(np.unique(idx)) != len(idx) or idx.min() < 0 or idx.max() >= values.shape[1]:
            raise ValueError(f"Invalid vertex indices for ROI {name}")
        names.append(name)
        arrays.append(values[:, idx].mean(axis=1))
    if not names:
        raise ValueError("Supply verified ROIs; the tool never invents auditory/language boundaries")
    return np.stack(arrays, axis=1), names


def summarize(values, starts, durations, names, start=None, end=None):
    values, starts, durations = map(lambda x: np.asarray(x, dtype=float), (values, starts, durations))
    if values.ndim != 2 or values.shape != (len(starts), len(names)) or durations.shape != starts.shape or not len(starts):
        raise ValueError("ROI rows and timestamp shapes do not match")
    if not all(np.isfinite(x).all() for x in (values, starts, durations)) or np.any(durations <= 0) or np.any(starts < 0) or np.any(np.diff(starts) < 0):
        raise ValueError("Invalid ROI values or timestamps")
    if np.any(starts[1:] < (starts + durations)[:-1] - 1e-6):
        raise ValueError("Overlapping prediction windows must be reconciled before calibration")
    start = float(starts[0] if start is None else start)
    end = float(np.max(starts + durations) if end is None else end)
    if not math.isfinite(start + end) or start < 0 or end <= start:
        raise ValueError("Invalid clip range")
    weights = np.maximum(0, np.minimum(starts + durations, end) - np.maximum(starts, start))
    if not np.any(weights):
        raise ValueError("No TRIBE timestep overlaps this clip")
    if weights.sum() < .9 * (end - start):
        raise ValueError("Less than 90% prediction coverage for this clip; do not fill gaps with invented activity")
    features, feature_names = [], []
    # Weighted statistics retain native TRIBE scale; z-scoring is fit later on train only.
    for i, name in enumerate(names):
        v, w = values[weights > 0, i], weights[weights > 0]
        mean = np.average(v, weights=w)
        stats = {"mean": mean, "variance": np.average((v - mean)**2, weights=w),
                 "min": v.min(), "max": v.max(), "peak_abs": np.abs(v).max()}
        for key, value in stats.items():
            features.append(float(value)); feature_names.append(f"{name}:{key}")
    return features, feature_names


def load_samples(manifest_path):
    manifest = read_json(manifest_path)
    if manifest.get("unit") not in {"video", "segment"}:
        raise ValueError("Declare unit=video or segment; video labels cannot validate segment scores")
    if not manifest.get("guideline_version") or not manifest.get("dimensions"):
        raise ValueError("Declare a guideline version and explicit dimensions/scales/targets")
    for dim, spec in manifest["dimensions"].items():
        lo, hi = spec["scale"]
        a, b = spec["target"]
        if not all(math.isfinite(float(v)) for v in (lo, hi, a, b)) or not lo < hi or not lo <= a <= b <= hi or not spec.get("guideline_id"):
            raise ValueError(f"Invalid scale, target or guideline ID for {dim}")
    samples, seen, signatures = [], set(), set()
    video_groups, hashes = {}, {}
    base = Path(manifest_path).resolve().parent
    for entry in manifest.get("samples", []):
        if not entry.get("id") or entry["id"] in seen:
            raise ValueError("Each sample needs a unique id")
        seen.add(entry["id"])
        for key in ("video_id", "group_id", "language"):
            if not entry.get(key): raise ValueError(f"Missing {key}")
        video = entry["video_id"]
        if video in video_groups and video_groups[video] != entry["group_id"]:
            raise ValueError("Every segment/variant of a video must stay in the same split group")
        video_groups[video] = entry["group_id"]
        path = base / entry["prediction_file"]
        meta = read_json(path.with_suffix(".json"))
        if meta.get("model") != "facebook/tribev2" or meta.get("language") != entry["language"] or not meta.get("signature") or not meta.get("video_sha256"):
            raise ValueError("Missing or mismatched TRIBE prediction provenance/language")
        vid_hash = meta["video_sha256"]
        if vid_hash in hashes and hashes[vid_hash] != video:
            raise ValueError("Identical video bytes cannot count as independent videos")
        hashes[vid_hash] = video
        signatures.add(meta["signature"])
        bounds = (entry.get("start"), entry.get("end"))
        if manifest["unit"] == "segment" and None in bounds:
            raise ValueError("Segment ratings need explicit original-video start/end")
        if manifest["unit"] == "video" and any(v is not None for v in bounds):
            raise ValueError("Video labels require whole-video features")
        with np.load(path, allow_pickle=False) as data:
            x, names = summarize(data["roi_values"], data["starts"], data["durations"], meta["roi_names"], *bounds)
        native_raters = manifest.get("native_raters", {}).get(entry["language"], [])
        if len(native_raters) != 2 or len(set(native_raters)) != 2:
            raise ValueError("Declare two distinct native raters per language")
        ratings = []
        for dim, spec in manifest["dimensions"].items():
            row = entry.get("ratings", {}).get(dim, {})
            pair = [row.get(r) for r in native_raters]
            if any(type(v) not in (int, float) or not math.isfinite(v) or not spec["scale"][0] <= v <= spec["scale"][1] for v in pair):
                raise ValueError(f"Two finite native ratings on the declared scale are required: {entry['id']}/{dim}")
            ratings.append(pair)
        samples.append(dict(entry, x=x, y=ratings, video_sha256=vid_hash, feature_names=names))
    if not samples or len(signatures) != 1:
        raise ValueError("Need samples from one matching checkpoint/ROI/text-ablation configuration")
    if manifest["unit"] == "video" and len({s['video_id'] for s in samples}) != len(samples):
        raise ValueError("Only one whole-video sample per video")
    if any(s["feature_names"] != samples[0]["feature_names"] for s in samples):
        raise ValueError("Feature ordering differs between samples")
    return manifest, samples, signatures.pop()


def fit_ridge(x, y, weights, alpha):
    w = weights / weights.sum()
    mean = np.sum(x * w[:, None], axis=0)
    scale = np.sqrt(np.sum((x - mean)**2 * w[:, None], axis=0))
    scale[scale < 1e-8] = 1
    z = (x - mean) / scale
    intercept = np.sum(y * w[:, None], axis=0)
    coef = np.linalg.solve(z.T @ (z * weights[:, None]) + alpha * np.eye(x.shape[1]),
                           z.T @ ((y - intercept) * weights[:, None]))
    return {"mean": mean.tolist(), "scale": scale.tolist(), "coef": coef.tolist(), "intercept": intercept.tolist()}


def predict(model, x):
    return ((np.asarray(x) - model["mean"]) / model["scale"]) @ np.asarray(model["coef"]) + model["intercept"]


def video_weights(rows):
    counts = {v: sum(r["video_id"] == v for r in rows) for v in {r["video_id"] for r in rows}}
    return np.array([1 / counts[r["video_id"]] for r in rows])


def holdout_groups(rows, seed):
    """Choose a group-preserving split closest to exactly 20% of videos."""
    groups = np.array(sorted({r["group_id"] for r in rows}))
    if len(groups) < 10:
        raise ValueError("Need at least 10 independent creator/campaign groups for grouped validation")
    np.random.default_rng(seed).shuffle(groups)
    target = round(.2 * len({r["video_id"] for r in rows}))
    possible = {0: []}
    for group in groups:
        size = len({r["video_id"] for r in rows if r["group_id"] == group})
        for n, picked in list(possible.items()):
            if len(picked) + 1 <= len(groups) - 5:
                candidate = picked + [str(group)]
                if n+size not in possible or len(candidate) < len(possible[n+size]):
                    possible[n+size] = candidate
    best = min((n for n in possible if n > 0), key=lambda n: (abs(n-target),n))
    test = set(possible[best])
    return test, np.array([g for g in groups if g not in test])


def metrics(a, b, weights):
    a, b = np.asarray(a), np.asarray(b)
    w = weights / weights.sum()
    ac, bc = a - np.sum(a * w), b - np.sum(b * w)
    denom = np.sqrt(np.sum(ac**2*w) * np.sum(bc**2*w))
    return {"pearson": float(np.sum(ac*bc*w)/denom) if denom > 1e-12 else None,
            "agreement_within_1": float(np.sum((np.abs(a-b) <= 1)*w)),
            "mae": float(np.sum(np.abs(a-b)*w)), "bias": float(np.sum((a-b)*w))}


def train(manifest_path, output, seed=42):
    manifest, samples, signature = load_samples(manifest_path)
    result = {"model": "TRIBE ROI ridge calibration", "unit": manifest["unit"],
              "signature": signature, "feature_names": samples[0]["feature_names"],
              "guideline_version": manifest["guideline_version"], "dimensions": manifest["dimensions"],
              "seed": seed, "languages": {}, "below_80_percent": [],
              "note": "Measured only on supplied labeled data. Per-language train-only z-scores. Held-out data is never used for fitting or alpha selection. No guaranteed tone/guideline meaning or virality."}
    for language in sorted({s["language"] for s in samples}):
        rows = [s for s in samples if s["language"] == language]
        videos = {r["video_id"] for r in rows}
        if len(videos) < 100:
            raise ValueError(f"{language}: need at least 100 distinct native-rated videos; found {len(videos)}. No calibration fitted.")
        test_groups, train_groups = holdout_groups(rows, seed)
        train_rows = [r for r in rows if r["group_id"] not in test_groups]
        test_rows = [r for r in rows if r["group_id"] in test_groups]
        x = np.array([r["x"] for r in train_rows]); y = np.array([r["y"] for r in train_rows]).mean(axis=2)
        w = video_weights(train_rows)
        # Grouped 5-fold tuning inside training only, including scaler fitting.
        losses = {}
        for alpha in (.1, 1., 10., 100.):
            errors = []
            for validation_groups in np.array_split(train_groups, 5):
                hold = np.array([r["group_id"] in validation_groups for r in train_rows])
                fitted = fit_ridge(x[~hold], y[~hold], w[~hold], alpha)
                errors.append(float(np.average(((predict(fitted,x[hold])-y[hold])**2).mean(axis=1),weights=w[hold])))
            losses[alpha] = np.mean(errors)
        alpha = min(losses, key=losses.get)
        fitted = fit_ridge(x, y, w, alpha)
        tx = np.array([r["x"] for r in test_rows]); ty = np.array([r["y"] for r in test_rows]); tw = video_weights(test_rows)
        raw = predict(fitted, tx)
        evaluation, worst = {}, []
        for j, (dim, spec) in enumerate(manifest["dimensions"].items()):
            pred = np.clip(raw[:, j], *spec["scale"]); target = ty[:, j, :].mean(axis=1)
            measured = metrics(pred, target, tw)
            evaluation[dim] = {"model_vs_mean_raters": measured,
                               "model_vs_rater_1": metrics(pred,ty[:,j,0],tw),
                               "model_vs_rater_2": metrics(pred,ty[:,j,1],tw),
                               "inter_rater": metrics(ty[:,j,0],ty[:,j,1],tw),
                               "training_mean_baseline": metrics(np.full(len(target),np.average(y[:,j],weights=w)),target,tw)}
            if measured["agreement_within_1"] < .8:
                result["below_80_percent"].append({"language": language, "dimension": dim})
            for i, r in enumerate(test_rows):
                worst.append({"sample_id":r["id"],"dimension":dim,"prediction":float(pred[i]),"human_mean":float(target[i]),"absolute_error":float(abs(pred[i]-target[i]))})
        result["languages"][language] = {"ridge": fitted, "alpha":alpha, "evaluation":evaluation,
            "train_ids":[r["id"] for r in train_rows],"test_ids":[r["id"] for r in test_rows],
            "train_video_hashes":sorted({r["video_sha256"] for r in train_rows}),
            "test_video_hashes":sorted({r["video_sha256"] for r in test_rows}),
            "train_groups":list(train_groups),"test_groups":sorted(test_groups),
            "train_videos":len({r["video_id"] for r in train_rows}),"test_videos":len({r["video_id"] for r in test_rows}),
            "held_out_video_fraction":len({r["video_id"] for r in test_rows})/len(videos),
            "split_note":"20% of videos held out where possible; nearest feasible group-preserving split otherwise, with actual fraction disclosed.",
            "worst_errors":sorted(worst,key=lambda e:e["absolute_error"],reverse=True)[:20]}
    write_json(output, result)
    lines=["# TRIBE calibration evaluation", "", "Held-out measurements on supplied labels, not a promised performance level.", "",
           "| Language | Dimension | Test videos | Pearson vs human mean | Within +/-1 | Inter-rater within +/-1 | Status |",
           "| --- | --- | ---: | ---: | ---: | ---: | --- |"]
    for lang, entry in result["languages"].items():
        for dim, row in entry["evaluation"].items():
            m=row["model_vs_mean_raters"];r=m["pearson"]
            lines.append(f"| {lang} | {dim} | {entry['test_videos']} | {round(r,3) if r is not None else 'undefined (constant values)'} | {m['agreement_within_1']:.1%} | {row['inter_rater']['agreement_within_1']:.1%} | {'below 80%' if m['agreement_within_1']<.8 else '>=80% point estimate'} |")
    lines += ["", "See the JSON for split IDs, train-only normalization, actual held-out fraction, individual-rater agreement, mean baseline, biases and worst errors. Small test sets have uncertain agreement estimates. A high within-one score on a narrow rating scale can be easy to achieve; consider correlation, MAE, baseline and rater reliability together."]
    Path(output).with_suffix(".md").write_text("\n".join(lines),encoding="utf-8")
    return result


def score_sample(artifact, language, x, signature, unit, guideline_version):
    if signature != artifact["signature"] or unit != artifact["unit"] or guideline_version != artifact["guideline_version"]:
        raise ValueError("Calibration does not match these features, scoring unit or guideline version")
    if language not in artifact["languages"]:
        raise ValueError("No fitted calibration for this language; no English fallback score")
    x = np.asarray(x,dtype=float)
    if x.shape != (len(artifact["feature_names"]),) or not np.isfinite(x).all():
        raise ValueError("Invalid feature vector")
    values = predict(artifact["languages"][language]["ridge"], x)
    return {dim:float(np.clip(v,*spec["scale"])) for (dim,spec),v in zip(artifact["dimensions"].items(),values)}
