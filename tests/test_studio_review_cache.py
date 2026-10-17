import unittest

from studio_review_cache import CompletionCache


class CompletionCacheTests(unittest.TestCase):
    def test_first_attempt_cannot_erase_corrected_retry_after_restart(self):
        old = {"signature": "same-video", "parts": {"rating": {
            "prompt_hash": "corrective-prompt", "result": {"grade": 3, "source_ids": ["S1"]}}}}
        cache = CompletionCache(old, "same-video")
        self.assertIsNone(cache.get("rating", "initial-prompt"))
        cache.remember("rating", "initial-prompt", {"grade": 2})
        restarted = CompletionCache(cache.snapshot(), "same-video")
        self.assertEqual(restarted.get("rating", "corrective-prompt")["result"]["source_ids"], ["S1"])
        self.assertEqual(restarted.get("rating", "initial-prompt")["result"], {"grade": 2})

    def test_changed_evidence_does_not_reuse_results(self):
        cache = CompletionCache({}, "video-one")
        cache.remember("rating", "prompt", {"grade": 3})
        changed = CompletionCache(cache.snapshot(), "video-two")
        self.assertIsNone(changed.get("rating", "prompt"))

    def test_validation_mutations_do_not_change_saved_results(self):
        cache = CompletionCache({}, "video")
        cache.remember("rating", "prompt", {"source_ids": ["S1"]})
        cache.get("rating", "prompt")["result"]["source_ids"].append("invented")
        self.assertEqual(cache.get("rating", "prompt")["result"]["source_ids"], ["S1"])
