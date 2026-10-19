import copy
import io
import json
import tempfile
import unittest
import urllib.error
from datetime import datetime, timezone, timedelta
from unittest.mock import patch
from pathlib import Path
import studio_script_performance as p
from studio_script_hf import HostedWriterError


def dataset(count=20):
    return {'account':'test-account','outcome_definition':'3-second retention >= 65% at 24h','measurement_window_hours':24,
        'rows':[{'post_id':str(i),'niche':'skincare','language':'Hinglish','platform':'Instagram Reels','duration':30,
                 'script_text':'Mujhe bas ek simple routine chahiye. Yaar itna confusion kyun hai? Private script text.',
                 'published_at':'2026-01-01T00:00:00Z','observed_at':'2026-01-02T00:00:00Z','label':bool(i%2)} for i in range(count)]}


def brief():
    return {'niche':'skincare','language':'Hinglish','platform':'Instagram Reels','duration':30}


class Response(io.BytesIO): status=200


class PerformanceTests(unittest.TestCase):
    def test_requires_real_boolean_labels_past_outcomes_and_fixed_window(self):
        for changes in [{'label':80},{'label':'true'},{'observed_at':'2099-01-01T00:00:00Z'},
                        {'observed_at':'2026-01-01T01:00:00Z'},{'published_at':'2026-01-01'},
                        {'duration':True},{'script_text':''}]:
            d=dataset();d['rows'][0].update(changes)
            with self.subTest(changes=changes),self.assertRaises(ValueError):p.validate_dataset(d)
        d=dataset();d['rows'][1]['post_id']='0'
        with self.assertRaisesRegex(ValueError,'Duplicate'):p.validate_dataset(d)
        self.assertEqual(len(p.validate_dataset(dataset())['rows']),20)

    def test_cohort_gates_prevent_manufactured_predictions(self):
        for changes in ({'niche':'arcade'},{'language':'English'},{'platform':'YouTube Shorts'},{'duration':60}):
            with self.assertRaisesRegex(ValueError,'at least 20'):
                p.build_payload(p.validate_dataset(dataset()),dict(brief(),**changes),'Candidate')
        d=dataset();d['rows'][0]['label']=False
        for r in d['rows']:r['label']=False
        with self.assertRaises(ValueError):p.build_payload(p.validate_dataset(d),brief(),'Candidate')

    def test_payload_no_raw_text_account_identifiers_or_future_outcome_features(self):
        payload,details=p.build_payload(p.validate_dataset(dataset()),brief(),'New private candidate text')
        wire=json.dumps(payload)
        self.assertNotIn('Private script',wire)
        self.assertNotIn('New private candidate',wire)
        self.assertNotIn('test-account',wire)
        self.assertNotIn('retention',wire)
        feature_columns=payload['context']['related_tables']['scripts']['columns']
        for forbidden in ('label','views','likes','shares','observed_at'):
            self.assertNotIn(forbidden,feature_columns)
        self.assertEqual(payload['predict']['instance_table']['rows'][0][0],20)
        self.assertNotIn('label',payload['predict']['instance_table']['columns'])
        self.assertEqual(details['context_rows'],20)
        self.assertEqual(details['base_rate'],.5)

    def test_probability_response_matches_requested_row_and_valid_range(self):
        for probs in ({'false':.3,'true':.7},[.3,.7],[{'class':'true','probability':.7}]):
            self.assertEqual(p.probability_from_response({'predictions':[{'row_index':0,'probabilities':probs}]}),.7)
        for data in ({},{'predictions':[]},{'predictions':[{'row_index':1,'probabilities':{'true':.7}}]},
                     {'predictions':[{'row_index':0,'probabilities':{'true':float('nan')}}]},
                     {'predictions':[{'row_index':0,'probabilities':{'true':1.1}}]}):
            with self.assertRaises(HostedWriterError):p.probability_from_response(data)

    def test_transport_keeps_key_out_of_result_and_marks_uncalibrated(self):
        response={'predictions':[{'row_index':0,'probabilities':{'false':.4,'true':.6}}]}
        with patch.object(p,'nvidia_token',return_value='nvapi-TESTSECRET'),patch.object(p.urllib.request,'urlopen') as send:
            send.return_value.__enter__.return_value=Response(json.dumps(response).encode())
            result=p.predict(p.validate_dataset(dataset()),brief(),'Candidate speech')
            self.assertFalse(result['calibrated'])
            self.assertEqual(result['probability'],.6)
            self.assertNotIn('nvapi-TESTSECRET',json.dumps(result))
            self.assertEqual(send.call_count,1)
        error=urllib.error.HTTPError(p.ENDPOINT,429,'nvapi-TESTSECRET',None,None)
        with patch.object(p,'nvidia_token',return_value='nvapi-TESTSECRET'),patch.object(p.urllib.request,'urlopen',side_effect=error):
            with self.assertRaises(HostedWriterError) as caught:p.predict(p.validate_dataset(dataset()),brief(),'Candidate')
            self.assertNotIn('nvapi-TESTSECRET',str(caught.exception))


if __name__=='__main__': unittest.main()
