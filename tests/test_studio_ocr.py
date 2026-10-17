"""Regressions for visual CTA evidence, speech uncertainty and private frame access."""
import tempfile
import unittest
from pathlib import Path

from studio_ocr import select_evidence, reading_text, comment_link_ctas, trusted_groups
from studio_review import evidence, normalize_absence_evidence
from studio_estimate import estimate_score
from studio_evaluation import build_evaluation
from studio_screenshots import screenshot_path
from studio_review_parts import protected_screen_quotes, recognition_penalty, contradicts_known_cta
from studio_pipeline import timed_speech_segments


class ScreenEvidenceTests(unittest.TestCase):
    def test_weak_packaging_readings_are_not_scoring_evidence(self):
        frames=[{'time_seconds':36,'frame_file':'ocr_frames/frame_0036.jpg','lines':[
            {'text':'YMOTANAJAAR','confidence':.71}, {'text':"COMMENT DUO FOR LINK",'confidence':.98}]}]
        groups=trusted_groups(frames,38)
        self.assertEqual(groups[0]['text'],'COMMENT DUO FOR LINK')
        self.assertEqual(len(frames[0]['lines']),2)
        self.assertTrue(recognition_penalty('The message is weakened by fragmented, noisy overlays.'))
        self.assertFalse(recognition_penalty('OCR confirms the CTA. The opening delays the audience problem.'))
        self.assertTrue(contradicts_known_cta("Confusing CTA keyword DUO in OCR"))
        self.assertFalse(contradicts_known_cta("The CTA gives a clear action; the reason to act could be stronger."))

    def test_long_asr_spans_split_without_translating_or_losing_words(self):
        words=[{'start':i,'end':i+.5,'word':w,'probability':.9} for i,w in enumerate(['मेरे','salon','bhaiya.','पैसा','वसूल','shampoo','and','mask','today'])]
        rows=timed_speech_segments(0,8.5,'unused recognition formatting',words)
        self.assertEqual([w for r in rows for w in r['words']],words)
        self.assertEqual(rows[0]['text'],'मेरे salon bhaiya.')
        self.assertTrue(all(r['end']-r['start']<=5 for r in rows))

    def test_ocr_line_breaks_do_not_destroy_a_comment_keyword_cta(self):
        original="COMMENT | DUO'FOR | LINK | BARE ANATOMY"
        self.assertEqual(reading_text(original),"COMMENT DUO'FOR LINK BARE ANATOMY")
        sources=[{'id':'O22','kind':'ocr','text':original}]
        found=comment_link_ctas(sources)
        self.assertEqual(found[0]['keyword'],'DUO')
        self.assertEqual(found[0]['source_id'],'O22')
        self.assertEqual(comment_link_ctas([{'kind':'ocr','text':'COMMENT on this shampoo','id':'O1'}]),[])

    def test_exact_cta_survives_long_video_condensing(self):
        source={'id':'O22','start':35,'end':38,'kind':'ocr','confidence':.97,
                'text':"COMMENT | DUO'FOR | LINK | BARE ANATOMY | Shampoo | "+'small label '*100}
        quotes=protected_screen_quotes([source],lambda text:len(text)//4)
        self.assertEqual(quotes[0]['id'],'O22')
        self.assertTrue(quotes[0]['text'].startswith("COMMENT | DUO'FOR | LINK"))
        self.assertTrue(quotes[0]['excerpt'])
        self.assertNotIn('translation',quotes[0])

    def test_closing_cta_survives_busy_video_evidence_limit(self):
        rows=[dict(start=i,end=i+1,text=f'Other overlay {i}',confidence=.95,frame_file=f'ocr_frames/frame_{i:04}.jpg') for i in range(90)]
        rows[-1]['text']="COMMENT 'DUO' FOR LINK"
        rows[45]['text']='BARE ANATOMY DAMAGE REPAIR shampoo'
        selected=select_evidence(rows,90)
        self.assertLessEqual(len(selected),24)
        self.assertGreater(len(selected),0)
        self.assertIn(rows[-1]['text'],[r['text'] for r in selected])
        self.assertIn(rows[45]['text'],[r['text'] for r in selected])
        self.assertEqual(selected[-1]['kind'],'ocr')

    def test_clear_visual_cta_is_not_discounted_for_bad_speech(self):
        dimension={'key':'cta','grade':4,'weight':100,'source_ids':['O1'],
                   'rationale':'Closing OCR gives COMMENT DUO FOR LINK. Speech has recognition uncertainty.'}
        transcript={'language':'hi','segments':[{'words':[{'probability':.1}]*10}]}
        ocr={'sources':[{'id':'O1','confidence':.98}]}
        result=estimate_score([dimension],transcript,ocr)
        self.assertEqual(result['score'],100)
        self.assertFalse(result['dimensions'][0]['recognition_concern'])
        dimension['source_ids']=['S1']
        self.assertEqual(estimate_score([dimension],transcript,ocr)['score'],50)

    def test_original_language_and_typed_sources_survive_export(self):
        original='पैसा वसूल; salon bhaiya'
        report={'transcript':{'segments':[{'start':0,'end':3,'text':original}]},
                'ocr':{'sources':[{'id':'O1','start':28,'end':30,'text':"COMMENT 'DUO' FOR LINK",'kind':'ocr','confidence':.98}]}}
        sources=evidence(report)
        self.assertEqual(sources[0]['text'],original)
        self.assertEqual([s['kind'] for s in sources],['speech','ocr'])
        row={'grade':0,'source_ids':[]}
        normalize_absence_evidence(row,{s['id'] for s in sources})
        self.assertEqual(set(row['source_ids']),{'S1','O1'})
        self.assertEqual(row['evidence_scope'],'supplied_evidence_absence_check')
        exported=build_evaluation(report)
        self.assertIsNone(exported['performance_score'])
        self.assertEqual(exported['detected_on_screen_elements'][0]['text'],"COMMENT 'DUO' FOR LINK")

    def test_pdf_embeds_ocr_frames_without_allowing_arbitrary_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'ocr_frames').mkdir()
            frame=root/'ocr_frames/frame_0001.jpg';frame.write_bytes(b'jpeg')
            private=root/'private.jpg';private.write_bytes(b'private')
            self.assertEqual(screenshot_path({'file':'ocr_frames/frame_0001.jpg'},root),frame)
            self.assertIsNone(screenshot_path({'file':'ocr_frames/../private.jpg'},root))


if __name__=='__main__':unittest.main()
