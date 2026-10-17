import copy
import json
import unittest
from pathlib import Path

from studio_review import RUBRIC, review_command
from studio_review_parts import evidence_chunks, generate_parts, generate_bursts, omit_recognition_faults, polish_unsupported_edits, repeated_output


class ReviewPartsTests(unittest.TestCase):
    def test_ocr_misread_does_not_become_creative_rationale(self):
        rationale = ("The script repeats ingredients without a clear payoff. "
                     "OCR errors in the product name undermine branding.")
        self.assertEqual(omit_recognition_faults(rationale),
                         "The script repeats ingredients without a clear payoff.")

    def test_unsupported_edits_are_replaced_with_verifiable_directions(self):
        report = {"transcript": {"segments": [{"start": 0, "end": 4,
                   "text": "Plum shampoo kills microbes", "words": []}]},
                  "visual": {"sources": [{"id": "V1", "kind": "visual", "start": 0,
                               "end": 1, "text": "person by curtain"},
                              {"id": "V2", "kind": "visual", "start": 3,
                               "end": 4, "text": "person by curtain"}]}}
        raw = {"dimensions": [{"key": "credibility", "rationale": "The claim is not backed by proof"}],
               "edits": [
                   {"targets": ["credibility"], "replacement": "Helps reduce microbes"},
                   {"targets": ["cta"], "replacement": "COMMENT [PLUM SHAMPOO PRODUCT] FOR LINK"},
                   {"targets": ["visual"], "instruction": "Fix OCR spelling", "replacement": "Fix typo"}]}
        polish_unsupported_edits(raw, report)
        self.assertIn("Brand-approved", raw["edits"][0]["replacement"])
        self.assertEqual(raw["edits"][1]["replacement"], "COMMENT 'PLUM' FOR LINK")
        self.assertEqual(raw["edits"][2]["source_ids"], ["V1", "V2"])
        self.assertIn("product-use shot", raw["edits"][2]["instruction"])

    def test_slogan_cannot_receive_strong_cta_and_batch_keeps_valid_rows(self):
        report = {"video": {"duration_seconds": 8}, "transcript": {"language": "en", "segments": [
            {"start": 0, "end": 8, "text": "Do not rinse it. Resolve it."}]}}
        calls = []
        def complete(prompt, tokens, label):
            calls.append(label)
            if label.startswith("Part 1"):
                return {"summary": "Product slogan without a next action", "verdict": "Needs a clear next action",
                        "content_language": "English", "strengths": [{"title": "Memorable phrase",
                        "detail": "The slogan is short", "source_ids": ["S1"]}], "uncertainties": []}
            if label == "Part 2/3: all ratings":
                return {"dimensions": [{"key": key, "grade": 3 if key == "cta" else 2,
                         "rationale": "The source supports this assessment", "source_ids": ["S1"]}
                         for key, *_ in RUBRIC]}
            if label.startswith("Part 2/3: rating Call to action"):
                return {"grade": 1, "rationale": "The closing slogan has no viewer action or destination",
                        "source_ids": ["S1"]}
            if label.startswith("Part 3"):
                return {"title": "Add action", "operation": "insert", "source_ids": ["S1"],
                        "instruction": "Add a clear next step", "replacement": "Visit the approved page",
                        "english_gloss": "Visit the approved page", "why": "The slogan has no next step",
                        "verify": "Action and destination appear together"}
            self.fail(f"Unexpected regeneration: {label}")
        _, review = generate_parts(report, [], complete, lambda *_: None)
        self.assertEqual(next(row["grade"] for row in review["dimensions"] if row["key"] == "cta"), 1)
        self.assertEqual(sum(label.startswith("Part 2/3: rating") for label in calls), 1)

    def test_partial_unicode_generation_resumes_without_restarting_text(self):
        saved=[];interrupted=True
        def request(route,body,**kwargs):
            if route=='/apply-template':return {'prompt':'evidence'}
            if route=='/tokenize':return {'tokens':[10,11]}
            if route=='/detokenize':return {'content':'{"text":"हिं' if len(body['tokens'])==1 else '{"text":"हिंदी"}'}
            if body['n_predict']==0:return {}
            if body['prompt']==[10,11]:return {'tokens':[500],'stop_type':'limit'}
            self.assertEqual(body['prompt'],[10,11,500])
            if interrupted:raise RuntimeError('Simulated interruption')
            return {'tokens':[501],'stop_type':'eos'}
        cache={'save_partial':lambda tokens:saved.append(list(tokens))}
        with self.assertRaisesRegex(RuntimeError,'Simulated interruption'):
            generate_bursts(request,[],64,lambda _:None,'Test',cache_state=cache)
        self.assertEqual(saved,[[500]])
        interrupted=False
        result=generate_bursts(request,[],64,lambda _:None,'Test',cache_state={'resume_tokens':saved[-1]})
        self.assertEqual(result,{'text':'हिंदी'})

    def test_unicode_repetition_is_detected_without_rejecting_normal_copy(self):
        self.assertTrue(repeated_output('ஏன் ' * 20))
        self.assertFalse(repeated_output('A clear opening and a clear closing action.'))

    def test_unreliable_rewrite_does_not_discard_valid_ratings(self):
        report={"video":{"duration_seconds":8},"transcript":{"language":"ta","segments":[{"start":0,"end":8,"text":"Original speech"}]}}
        def complete(prompt,tokens,label):
            if label.startswith('Part 1'):
                return {"summary":"Assessment","verdict":"Check speech","content_language":"Tamil","strengths":[{"title":"Topic","detail":"Evidence","source_ids":["S1"]}],"uncertainties":[]}
            if label == 'Part 2/3: all ratings':
                return {'dimensions':[{'key':key,'grade':0,'rationale':'Feature not established','source_ids':[]} for key, *_ in RUBRIC]}
            if label.startswith('Part 2'):
                return {"grade":0,"rationale":"Feature not established","source_ids":[]}
            raise ValueError('Repeated text detected')
        raw,review=generate_parts(report,[],complete,lambda *_:None)
        self.assertEqual(len(review['dimensions']),len(RUBRIC))
        self.assertEqual(len(review['edits']),3)
        self.assertTrue(all('Native-language copy could not' in e['replacement'] for e in review['edits']))
        self.assertTrue(review['uncertainties'])
    def test_repeated_evidence_reuses_the_current_gpu_slot(self):
        prefills = []
        def request(route, body, **kwargs):
            if route == "/apply-template":
                return {"prompt": "same evidence"}
            if route == "/tokenize":
                return {"tokens": list(range(300))}
            if route == "/detokenize":
                return {"content": '{"ok":true}<|im_end|>'}
            if body["n_predict"] == 0:
                prefills.append(len(body["prompt"]))
                return {}
            return {"content": '{"ok":true}', "tokens": [500], "stop_type": "eos"}
        cache = {}
        for _ in range(2):
            self.assertEqual(generate_bursts(request, [], 32, lambda _: None, "Test", cache_state=cache), {"ok": True})
        self.assertEqual(prefills, [64, 128, 192, 256, 300])

    def test_prompt_and_multilingual_output_run_in_paused_bursts(self):
        calls, pauses = [], []
        def request(route, body, **kwargs):
            calls.append((route, body))
            if route == "/apply-template":
                return {"prompt": "formatted"}
            if route == "/tokenize":
                return {"tokens": list(range(300))}
            if route == "/detokenize":
                return {"content": '{"text":"हिंदी' if len(body["tokens"]) == 2 else '{"text":"हिंदी தமிழ்"}'}
            if body["n_predict"] == 0:
                return {}
            self.assertLessEqual(body["n_predict"], 16)
            if len(body["prompt"]) == 300:
                return {"content": '{"text":"हिं\ufffd', "tokens": [500, 501], "stop_type": "limit"}
            self.assertEqual(body["prompt"][-2:], [500, 501])
            return {"content": ' தமிழ்"}', "tokens": [502, 503], "stop_type": "eos"}
        result = generate_bursts(request, [], 64, pauses.append, "Test")
        self.assertEqual(result, {"text": "हिंदी தமிழ்"})
        prefill = [len(body["prompt"]) for route, body in calls if route == "/completion" and body["n_predict"] == 0]
        self.assertEqual(prefill, [64, 128, 192, 256, 300])
        self.assertEqual(len(pauses), 7)

    def test_context_overflow_stops_before_gpu_work(self):
        def request(route, body):
            if route == "/apply-template":
                return {"prompt": "formatted"}
            if route == "/tokenize":
                return {"tokens": [1] * 4090}
            self.fail("No inference should be started")
        with self.assertRaisesRegex(ValueError, "small GPU context"):
            generate_bursts(request, [], 64, lambda label: None, "Test")

    def test_all_criteria_and_weaknesses_are_generated_in_separate_requests(self):
        report = {"video": {"duration_seconds": 20}, "transcript": {"language": "hi", "segments": [
            {"start": 0, "end": 5, "text": "मूल भाषा में वीडियो"}]}}
        report["ocr"] = {"sources": [{"id": "O1", "start": 4, "end": 5,
                                      "kind": "ocr", "confidence": .99, "text": "SHOP NOW"}]}
        source = [{"id": "S1", **report["transcript"]["segments"][0]}]
        summary = {"summary": "Detailed summary", "verdict": "Improve", "content_language": "Hindi",
                   "strengths": [{"title": "Best part", "detail": "Evidence", "source_ids": ["S1"]}],
                   "uncertainties": [],
                   "narrative_breakdown": dict.fromkeys(("hook", "problem", "product", "resolution"), "Observed message"),
                   "linguistic_review": {"noted_slang": [], "spoken_accuracy": "Check the audio"}}
        edit = {"title": "Edit", "operation": "overlay", "source_ids": ["S1"],
                "instruction": "Change opening", "replacement": "बदलाव", "english_gloss": "Change",
                "why": "Clarify meaning", "verify": "One clear message"}
        calls, progress = [], []
        def complete(prompt, tokens, label):
            self.assertLessEqual(tokens, 1300)
            calls.append(label)
            if label.startswith("Part 1"):
                return copy.deepcopy(summary)
            if label == "Part 2/3: all ratings":
                return {"dimensions":[{"key":key,"grade":2,"rationale":"Evidence","source_ids":["S1"]} for key, *_ in RUBRIC]}
            if label.startswith("Part 2"):
                return {"grade": 2, "rationale": "Evidence", "source_ids": ["S1"]}
            if label.startswith("Part 3/3: improvement 2/"):
                prior = json.loads(prompt.split("Previous edits (avoid duplication): ", 1)[1].split("\n", 1)[0])
                self.assertEqual(prior[0]["source_ids"], ["S1"])
                self.assertEqual(prior[0]["operation"], "overlay")
                self.assertEqual(prior[0]["instruction"], "Change opening")
            return copy.deepcopy(edit)
        raw, review = generate_parts(report, source, complete, lambda fraction, label: progress.append(fraction))
        self.assertEqual(len(calls), 5)
        self.assertEqual(len(review["dimensions"]), len(RUBRIC))
        self.assertEqual(len(review["edits"]), 3)
        self.assertEqual({e["targets"][0] for e in review["edits"]}, {'visual','hook','clarity'})
        self.assertEqual(review["overall_score"], 50)
        self.assertEqual(progress, sorted(progress))

    def test_large_segments_are_split_without_losing_text_or_source_ids(self):
        original = "हिंदी தமிழ் తెలుగు " * 100
        chunks = evidence_chunks([{"id": "S1", "start": 0, "end": 10, "text": original}], len, limit=200)
        self.assertGreater(len(chunks), 1)
        self.assertEqual("".join(row["text"] for chunk in chunks for row in chunk), original)
        for chunk in chunks:
            self.assertLessEqual(len(json.dumps(chunk, ensure_ascii=False)), 200)
            self.assertTrue(all(row["id"] == "S1" for row in chunk))

    def test_review_runtime_full_gpu_small_context_no_host_cache(self):
        command = review_command(Path("llama-server.exe"), 12345)
        for flag, value in {"-ngl": "all", "--fit": "off", "-fa": "off", "-ctk": "f16",
                            "-ctv": "f16", "-c": "6144", "-b": "32", "-ub": "16",
                            "--cache-ram": "0", "--ctx-checkpoints": "0", "-np": "1", "--load-mode": "none"}.items():
            self.assertEqual(command[command.index(flag) + 1], value)
        self.assertIn("--no-host", command)
