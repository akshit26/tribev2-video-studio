import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import studio_script_team as team
import studio_video_learning as learning
from studio_script_research import values

class VideoLearningTests(unittest.TestCase):
    def test_stage_roles(self):
        self.assertEqual(team.stage_model('Draft 1'),team.MODEL)
        self.assertEqual(team.stage_model('Hook options 1'),team.MODEL)
        self.assertEqual(team.stage_model('Critique 1'),team.GEMMA)
        self.assertEqual(team.stage_model('Hook critique 1'),team.GEMMA)

    def test_links_and_input_validation(self):
        self.assertEqual(learning.canonical_video('https://youtu.be/abcdefghijk')[0],'youtube')
        for url in ['http://localhost/a','https://example.com/video','https://youtube.com.evil.org/watch?v=abcdefghijk']:
            with self.assertRaises(ValueError):learning.canonical_video(url)
        with self.assertRaises(ValueError):values({'topic':'skin','video_urls':[42]})
        self.assertEqual(values({'topic':'skin'})['research_mode'],'videos')

    def test_rules_recalled_only_for_matching_language_and_niche(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            brief={'niche':'skincare','language':'Hindi','topic':'Skin'}
            result={'researched_at':'2026-10-20','rules':[{'rule':'When a worry is specific, test an unexpected explanation.','limits':'A hypothesis','book_ids':['book']} ]}
            learning.remember(root,'research',brief,result)
            learning.remember(root,'research',brief,result)
            self.assertEqual(len(learning.recall(root,brief)),1)
            self.assertEqual(learning.recall(root,dict(brief,language='English')),[])
            self.assertNotIn('transcript',str(learning.recall(root,brief)))

    def test_missing_clips_never_fabricates_speech(self):
        with tempfile.TemporaryDirectory() as folder,patch.object(learning,'discover',return_value=([],[])),patch.object(learning,'analyze_mechanisms') as analyze:
            with self.assertRaisesRegex(ValueError,'No matching video speech'):
                learning.run_video_research({'upload_ids':[]},Path(folder),None,lambda x:None,lambda x:None)
            analyze.assert_not_called()

class MechanismEvidenceTests(unittest.TestCase):
    def test_evidence_must_overlap_real_transcribed_speech(self):
        from studio_script_writer import library
        book=next(c['id'] for c in library()['cards'] if c['kind']=='book')
        video={'id':'youtube_test','duration':30,'transcript':{'language':'en','segments':[{'start':2,'end':5,'text':'An actual speech event.'}]}}
        rule={'rule':'When the question is specific, delay its answer briefly.','explanation':'A hypothesis about curiosity.','limits':'Distribution is unknown.','book_ids':[book],'evidence':[{'video_id':'youtube_test','start':2,'end':4,'observation':'The speaker asks a specific question.'}]}
        answer={'summary':'Observed words only.','rules':[rule]}
        with patch.object(team,'chat_json',return_value=(answer,{})):
            result=learning.analyze_mechanisms({'language':'English'},[video])
            self.assertEqual(result['rules'][0]['book_ids'],[book])
            rule['evidence'][0]['start']=10;rule['evidence'][0]['end']=12
            with self.assertRaisesRegex(ValueError,'no transcribed speech'):
                learning.analyze_mechanisms({'language':'English'},[video])
