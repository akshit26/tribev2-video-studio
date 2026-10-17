"""A missing citation field must not discard a usable, unchanged assessment."""
import copy
import unittest

from studio_review_parts import generate_parts


class CitationRecoveryTests(unittest.TestCase):
    def run_review(self, selection, omit_edit_sources=False, edit_changes=None):
        report={'video':{'duration_seconds':20},'transcript':{'language':'en','segments':[
            {'start':0,'end':3,'text':'My hair was dry.'},
            {'start':10,'end':15,'text':'My hair feels softer now. Shop now.'}]},
            'ocr':{'sources':[{'id':'O1','start':10,'end':12,'kind':'ocr','confidence':.98,'text':'Softer hair'}]}}
        summary={'summary':'A product testimonial.','verdict':'Clear message','content_language':'English',
                 'strengths':[{'title':'Specific benefit','detail':'The speaker describes softer hair.','source_ids':['S2']}],
                 'uncertainties':[],'narrative_breakdown':dict.fromkeys(('hook','problem','product','resolution'),'A product testimonial.'),
                 'linguistic_review':{'noted_slang':[],'spoken_accuracy':'Check the original audio.'}}
        rationale='The product message and softer-hair payoff are clear.'
        edit={'title':'Clarify the demonstration','operation':'overlay','source_ids':['S2'],
              'instruction':'Label the visible result.','replacement':'Softer hair','english_gloss':'Softer hair',
              'why':'Connect the message and result.','verify':'The caption matches the spoken testimonial.'}
        if omit_edit_sources:edit.pop('source_ids')
        if edit_changes:edit.update(edit_changes)
        calls=[]
        def complete(prompt,tokens,label):
            calls.append(label)
            if label.endswith('/ citation selection'):
                self.assertIn('ALLOWED_IDS:',prompt)
                if label.startswith('Part 2'):self.assertIn(rationale,prompt)
                else:self.assertIn('PROPOSED EDIT',prompt)
                return copy.deepcopy(selection)
            if label.startswith('Part 1'):return copy.deepcopy(summary)
            if label.startswith('Part 2'):
                row={'grade':2 if ('Voice and delivery' in label or 'Visual presentation' in label) else 3,
                     'rationale':rationale,'source_ids':['S2']}
                if 'Script and payoff' in label:row.pop('source_ids')
                return row
            return copy.deepcopy(edit)
        return generate_parts(report,[],complete,lambda *_:None),calls,rationale

    def test_missing_field_is_repaired_without_changing_grade_or_reason(self):
        (raw,review),calls,rationale=self.run_review({'source_ids':['S2','O1'],'grade':4})
        row=next(d for d in review['dimensions'] if d['key']=='clarity')
        self.assertEqual(row['grade'],3)
        self.assertEqual(row['rationale'],rationale)
        self.assertEqual(row['source_ids'],['S2','O1'])
        self.assertIsNone(next(d for d in raw['dimensions'] if d['key']=='clarity')['citation_repair']['original_source_ids'])
        self.assertEqual(sum(c.endswith('/ citation selection') for c in calls),1)

    def test_invented_id_is_not_silently_dropped_or_replaced(self):
        with self.assertRaisesRegex(ValueError,'Citation repair could not establish valid evidence'):
            self.run_review({'source_ids':['S2','O999']})

    def test_empty_selection_cannot_turn_into_fabricated_support(self):
        with self.assertRaisesRegex(ValueError,'Citation repair could not establish valid evidence'):
            self.run_review({'source_ids':[]})

    def test_edit_anchor_is_recovered_without_rewriting_proposed_copy(self):
        (raw,review),_,_=self.run_review({'source_ids':['S2']},omit_edit_sources=True)
        self.assertEqual(len(review['edits']),3)
        for edit in review['edits']:
            self.assertEqual(edit['replacement'],'Softer hair')
            self.assertEqual(edit['source_ids'],['S2'])
            self.assertEqual((edit['start'],edit['end']),(10,15))
        self.assertTrue(all('citation_repair' in e for e in raw['edits']))

    def test_valid_citation_cannot_launder_an_invented_free_offer(self):
        (_,review),_,_=self.run_review({'source_ids':['S2']},edit_changes={'replacement':'Comment PLUM for your free dandruff care guide.'})
        self.assertTrue(all('Native-language copy could not' in e['replacement'] for e in review['edits']))
        self.assertNotIn('free dandruff care guide',str(review['edits']))

    def test_recognition_defect_cannot_become_a_creative_edit(self):
        (_,review),_,_=self.run_review({'source_ids':['S2']},edit_changes={'why':'Existing OCR is corrupted and makes the video unclear.'})
        self.assertTrue(all('Native-language copy could not' in e['replacement'] for e in review['edits']))

    def test_overlay_text_does_not_prove_a_claim_is_on_packaging(self):
        (_,review),_,_=self.run_review({'source_ids':['S2']},edit_changes={'replacement':'Softer hair, as stated on the bottle.'})
        self.assertTrue(all('Native-language copy could not' in e['replacement'] for e in review['edits']))


if __name__=='__main__':unittest.main()
