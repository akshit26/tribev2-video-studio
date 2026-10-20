import copy
import json
import unittest
from studio_script_language import normalize_language, language_issues, naturalness_issues, word_budget
from studio_script_examples import catalog, niche_for, selected_examples, example_guidance
import studio_script_writer as writer
from tests.test_studio_script_writer import brief, script, assessment


class MultilingualWriterTests(unittest.TestCase):
    def test_language_aliases_and_niches_validate(self):
        for raw, expected in [('hi','Hindi'),('हिंदी','Hindi'),('en','English'),('roman hindi','Hindi (Roman)'),('hinglish','Hinglish')]:
            self.assertEqual(writer.brief_values(dict(brief(),language=raw))['language'],expected)
        with self.assertRaises(ValueError):
            writer.brief_values(dict(brief(),niche='made-up'))

    def test_timing_gates_apply_to_hindi_and_hinglish(self):
        for language in ('English','Hindi','Hindi (Roman)','Hinglish'):
            b=dict(brief(),language=language)
            timing=writer.spoken_timing(script(),b)
            self.assertTrue(timing['estimate_available'])
            self.assertEqual((timing['minimum_words'],timing['target_words'],timing['maximum_words']),word_budget(b))
        self.assertEqual(word_budget(dict(brief(),language='Hindi',duration=30)),(54,66,84))
        short=script()
        for row in short['scenes']: row['spoken']='बस इतना।'
        self.assertTrue(writer.duration_issues(short,dict(brief(),language='Hindi')))

    def test_writing_system_and_actual_code_switching(self):
        english='This is an entirely English script about an ordinary daily routine and a small observation that has no Hindi phrasing whatsoever.'
        self.assertTrue(language_issues(english,{'language':'Hindi'}))
        self.assertTrue(language_issues(english,{'language':'Hinglish'}))
        self.assertFalse(language_issues('मुझे बस इतनी बात समझनी है कि रोज सुबह इतना सोचने की जरूरत क्यों है।',{'language':'Hindi'}))
        self.assertFalse(language_issues('Yaar mujhe bas yeh samajhna hai ki routine ko itna complicated kyun karna hai. Shelf pe jagah bhi nahi bachi.',{'language':'Hinglish'}))
        self.assertTrue(language_issues('मुझे बस इतनी बात समझनी है।',{'language':'Hindi (Roman)'}))

    def test_ai_cliches_block_organic_target_without_penalizing_plain_copy(self):
        s=script();s['scenes'][1]['spoken']+=' An invisible armor seals a silent vow.'
        b=brief()
        result=writer.validate_assessment(assessment(4),s,b)
        self.assertLess(result['score'],80)
        self.assertTrue(any('over-written' in b for b in result['blockers']))
        self.assertFalse(naturalness_issues('I need a pocket that actually fits my phone.',b))

    def test_reference_coverage_and_provenance(self):
        data=catalog();sources={s['id'] for s in data['sources']}
        self.assertEqual(len(data['sources']),10)
        self.assertEqual(len(data['examples']),10)
        for niche in ('skincare','fashion','arcade','food_drinks','fmcg'):
            rows=[r for r in data['examples'] if r['niche']==niche]
            self.assertEqual(len(rows),2)
            for row in rows:
                self.assertTrue(set(row['source_ids'])<=sources)
                self.assertEqual(set(row['scripts']),{'English','Hindi','Hinglish'})
                for language,spoken in row['scripts'].items():
                    self.assertFalse(language_issues(spoken,{'language':language}),row['id'])
                    self.assertFalse(naturalness_issues(spoken,{'content_mode':'organic'}))
        for source in data['sources']:
            self.assertTrue(source['evidence'])
            self.assertTrue(source['url'].startswith('https://'))

    def test_selection_matches_niche_and_language_not_just_english_translation(self):
        b=dict(brief(),niche='arcade',language='Hindi')
        self.assertTrue(all('arcade-' in r['id'] for r in selected_examples(b)))
        self.assertIn('mechanism',example_guidance(b))
        self.assertNotIn('One more try',example_guidance(b))
        self.assertEqual(niche_for({'topic':'सनस्क्रीन','facts':''}),'skincare')
        self.assertEqual(niche_for({'topic':'Lip balm','facts':'','niche':'fashion'}),'fashion')

    def test_hindi_hinglish_usage_and_pilling_claims_need_evidence(self):
        b=dict(brief(),topic='Everyday moisturiser',facts='A moisturiser.',language='Hinglish')
        self.assertTrue(writer.claim_issues('Teesra toh makeup ke neeche ball bana deta hai.',b))
        self.assertTrue(writer.claim_issues('Maine teen hafte use kiya aur result mila.',b))
        self.assertTrue(writer.claim_issues('मैंने ये लगाया और असर दिखा।',dict(b,language='Hindi')))
        self.assertTrue(writer.claim_issues('इसे बिना धोए छोड़ दो।',dict(b,topic='शैंपू',facts='शैंपू; लेबल के अनुसार इस्तेमाल करें।',language='Hindi')))
        self.assertFalse(writer.claim_issues('Teesra toh makeup ke neeche ball bana deta hai.',dict(b,creator_experience='The third product: makeup ke neeche ball bana deta hai.')))
        self.assertTrue(writer.claim_issues('One smells like coconut, use a pea-sized dollop.',dict(b,language='English')))
        self.assertFalse(writer.claim_issues('It smells like coconut.',dict(b,facts='Coconut scent.',language='English')))


if __name__=='__main__': unittest.main()
