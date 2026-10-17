"""Synthetic correctness tests only; these are NOT language-accuracy benchmarks."""
import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace

import numpy as np
import pandas as pd
import torch

from tribev2.language import language_code, whisperx_command, transcript_cache_path
from tribev2.demo_utils import TribeModel, get_audio_and_text_events
from tribe_calibration.core import (write_json, read_json, fingerprint, roi_series, summarize,
                                    fit_ridge, metrics, train, score_sample, holdout_groups)
from tribe_calibration.workflow import segment_report, creator_export, ablation_report, transcript_quality, comparison_report, export_prediction


class OriginalLanguageTests(unittest.TestCase):
    def test_native_context_preserves_wording_without_spacy_rewriting(self):
        words=['தமிழ்','नमस्ते','BrandX']
        events=pd.DataFrame([{'type':'Word','text':w,'language':'ta','start':i,'duration':.5,'timeline':'t','subject':'s'} for i,w in enumerate(words)])
        identity=lambda *a,**kw:lambda rows:rows
        with patch('tribev2.demo_utils.ExtractAudioFromVideo',identity),patch('tribev2.demo_utils.ChunkEvents',identity):
            output=get_audio_and_text_events(events,language='ta')
        self.assertEqual(output.text.tolist(),words)
        self.assertEqual(output.context.tolist(),['தமிழ்','தமிழ் नमस्ते','தமிழ் नमस्ते BrandX'])

    def test_transcription_never_requests_translation_or_dangling_alignment(self):
        for language,code in [('hindi','hi'),('tamil','ta'),('telugu','te'),('en','en')]:
            cmd=whisperx_command('original.mp4','out',language,'cuda','float16')
            self.assertEqual(cmd[cmd.index('--task')+1],'transcribe')
            self.assertEqual(cmd[cmd.index('--language')+1],code)
            self.assertEqual('--align_model' in cmd,code=='en')
        self.assertNotIn('--language',whisperx_command('x','out','auto','cuda','float16'))
        with self.assertRaises(ValueError):language_code('../en')

    def test_transcript_cache_is_language_and_source_specific(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'audio.wav';p.write_bytes(b'original')
            a=transcript_cache_path(p,'hi')
            self.assertNotEqual(a,transcript_cache_path(p,'en'))
            self.assertNotEqual(a,p.with_suffix('.tsv'))
            p.write_bytes(b'changed audio')
            self.assertNotEqual(a,transcript_cache_path(p,'hi'))

    def test_video_path_and_language_reach_event_builder_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'original.mp4';p.write_bytes(b'fixture')
            with patch('tribev2.demo_utils.get_audio_and_text_events',return_value='events') as builder:
                result=TribeModel.get_events_dataframe(SimpleNamespace(),video_path=str(p),language='ta',include_text=False)
            self.assertEqual(result,'events')
            self.assertEqual(builder.call_args.args[0].iloc[0].filepath,str(p))
            self.assertEqual(builder.call_args.kwargs,{'audio_only':True,'language':'ta'})

    def test_text_ablation_removes_events_and_scaling_hook_is_cleaned(self):
        class Brain(torch.nn.Module):
            def __init__(self):
                super().__init__();self.projectors=torch.nn.ModuleDict({'text':torch.nn.Identity()});self.device='cpu'
            def forward(self,batch):
                value=torch.ones(1,1,1)
                return self.projectors['text'](value) if 'Word' in captured['events'].type.values else torch.zeros_like(value)
        segment=SimpleNamespace(start=0,duration=1,ns_events=[1]);segment.copy=lambda **kw:segment
        batch=SimpleNamespace(segments=[segment]);batch.to=lambda _:batch
        captured={}
        def loaders(**kwargs):captured.update(kwargs);return {'all':[batch]}
        model=Brain();fake=SimpleNamespace(_model=model,data=SimpleNamespace(TR=1,get_loaders=loaders),remove_empty_segments=True)
        events=pd.DataFrame({'type':['Video','Audio','Word','Text','Sentence']})
        output,_=TribeModel.predict(fake,events,verbose=False,text_weight=0)
        self.assertEqual(captured['events'].type.tolist(),['Video','Audio']);self.assertEqual(output[0,0],0)
        output,_=TribeModel.predict(fake,events,verbose=False,text_weight=.5)
        self.assertEqual(output[0,0],.5);self.assertEqual(len(model.projectors['text']._forward_hooks),0)
        output,_=TribeModel.predict(fake,events,verbose=False,text_weight=1)
        self.assertEqual(output[0,0],1)


class CalibrationTests(unittest.TestCase):
    def test_export_keeps_stimulus_times_and_ablation_requires_same_windows(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=Path(tmp);video=d/'source.mp4';video.write_bytes(b'synthetic')
            atlas={'vertex_count':2,'vertex_order':'synthetic','provenance':'test fixture','rois':{'test':[0,1]}}
            def events(**kwargs):
                rows=[{'type':'Video'}]
                if kwargs['include_text']:rows.append({'type':'Word','start':0,'duration':1,'text':'வணக்கம்'})
                return pd.DataFrame(rows)
            def prediction(**kwargs):
                return np.array([[1,3],[2,4]]),[SimpleNamespace(start=i,duration=1) for i in (0,1)]
            fake=SimpleNamespace(get_events_dataframe=events,predict=prediction)
            for name,weight in [('full',1),('av',0)]:
                export_prediction(fake,video,d/f'{name}.npz',atlas,'ta',weight,'synthetic-checkpoint')
            with np.load(d/'full.npz') as a:self.assertEqual(a['starts'].tolist(),[0,1])
            self.assertEqual(read_json(d/'full.json')['transcript'][0]['text'],'வணக்கம்')
            write_json(d/'manifest.json',{'samples':[{'prediction_file':'full.npz'},{'prediction_file':'av.npz'}]})
            result=ablation_report(d/'manifest.json',d/'result.json')
            self.assertEqual(len(result['raw_temporal_stability']),2)
            np.savez(d/'av.npz',roi_values=[[2],[3]],starts=[1,2],durations=[1,1])
            with self.assertRaisesRegex(ValueError,'same video'):ablation_report(d/'manifest.json',d/'bad.json')

    def test_matched_diagnosis_never_maps_raw_amplitude_to_tone(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=Path(tmp);rows=[]
            for language,value in [('en',2),('ta',1)]:
                for i in range(10):
                    path=d/f'{language}{i}.npz';np.savez(path,roi_values=[[value],[value]],starts=[0,1],durations=[1,1])
                    write_json(path.with_suffix('.json'),{'model':'facebook/tribev2','language':language,'signature':'synthetic','roi_names':['test']})
                    rows.append({'match_id':str(i),'language':language,'prediction_file':path.name})
            write_json(d/'pairs.json',{'samples':rows})
            result=comparison_report(d/'pairs.json',d/'report.json')
            self.assertEqual(result['comparisons']['ta']['roi_features']['test:mean']['paired_difference'],-1)
            self.assertIn('Unresolved',result['comparisons']['ta']['attribution'])
            rows.append(rows[0]);write_json(d/'pairs.json',{'samples':rows})
            with self.assertRaisesRegex(ValueError,'Duplicate'):comparison_report(d/'pairs.json',d/'bad.json')

    def test_roi_validation_and_overlap_weighted_features(self):
        p=np.array([[1,3,9],[3,5,7]],float)
        atlas={'vertex_count':3,'vertex_order':'verified test order','provenance':'synthetic','rois':{'auditory':[0,1]}}
        v,n=roi_series(p,atlas)
        x,names=summarize(v,[0,1],[1,1],n,.5,1.5)
        self.assertEqual(x,[3.,1.,2.,4.,4.])
        with self.assertRaises(ValueError):roi_series(p,dict(atlas,vertex_count=4))
        with self.assertRaises(ValueError):summarize(v,[0,2],[1,1],n,0,3)
        with self.assertRaises(ValueError):summarize(v,[0,.5],[1,1],n)

    def test_train_only_normalization_and_undefined_constant_correlation(self):
        fitted=fit_ridge(np.array([[1.],[3.]]),np.array([[1.],[5.]]),np.ones(2),1)
        self.assertEqual(fitted['mean'],[2.]);self.assertEqual(fitted['scale'],[1.])
        self.assertIsNone(metrics([1,1],[1,2],np.ones(2))['pearson'])

    def test_grouped_holdout_targets_twenty_percent_without_creator_leakage(self):
        rows=[{'video_id':str(i),'group_id':str(i//5)} for i in range(100)]
        held,training=holdout_groups(rows,42)
        self.assertEqual(sum(r['group_id'] in held for r in rows),20)
        self.assertFalse(held & set(training))

    def test_synthetic_fit_is_separate_from_real_agreement_and_rejects_small_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=Path(tmp);samples=[]
            for i in range(100):
                value=(i%5)+1.;path=d/f'{i}.npz'
                np.savez(path,roi_values=np.array([[value],[value+.1]]),starts=[0.,1.],durations=[1.,1.])
                write_json(path.with_suffix('.json'),{'model':'facebook/tribev2','language':'hi','signature':'synthetic-fixture','roi_names':['test_roi'],'video_sha256':str(i)})
                samples.append({'id':str(i),'video_id':str(i),'group_id':str(i),'language':'hi','prediction_file':path.name,'ratings':{'energy':{'a':value,'b':value}}})
            manifest={'unit':'video','guideline_version':'synthetic-v1','dimensions':{'energy':{'scale':[1,5],'target':[3,5],'guideline_id':'intro'}},'native_raters':{'hi':['a','b']},'samples':samples}
            source=d/'manifest.json';write_json(source,manifest)
            result=train(source,d/'model.json');lang=result['languages']['hi']
            self.assertEqual(lang['test_videos'],20);self.assertFalse(set(lang['train_ids']) & set(lang['test_ids']))
            # Recompute scaler reference only from the persisted training IDs.
            expected=np.mean([(int(i)%5)+1+.05 for i in lang['train_ids']])
            self.assertAlmostEqual(lang['ridge']['mean'][0],expected)
            with self.assertRaisesRegex(ValueError,'No fitted calibration'):
                score_sample(result,'ta',[0]*5,'synthetic-fixture','video','synthetic-v1')
            with self.assertRaises(ValueError):score_sample(result,'hi',[0]*5,'synthetic-fixture','segment','synthetic-v1')
            manifest['samples']=samples[:10];write_json(source,manifest)
            with self.assertRaisesRegex(ValueError,'at least 100'):train(source,d/'unfitted.json')
            self.assertFalse((d/'unfitted.json').exists())

    def test_segment_export_withholds_unreviewed_or_edited_suggestions(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=Path(tmp);pred=d/'pred.npz';np.savez(pred,roi_values=[[0],[0]],starts=[0,1],durations=[1,1])
            write_json(pred.with_suffix('.json'),{'language':'hi','signature':'synthetic','roi_names':['test'],
                       'video_sha256':'video','transcript':[{'start':0,'end':1,'text':'नमस्ते'}]})
            art={'unit':'segment','signature':'synthetic','guideline_version':'g1','feature_names':[f'test:{s}' for s in ('mean','variance','min','max','peak_abs')],
                 'dimensions':{'energy':{'scale':[1,5],'target':[3,5],'guideline_id':'intro'}},
                 'languages':{'hi':{'ridge':{'mean':[0]*5,'scale':[1]*5,'coef':[[0]]*5,'intercept':[1]}}}}
            write_json(d/'model.json',art);write_json(d/'clips.json',[{'start':0,'end':2}])
            write_json(d/'rules.json',{'guideline_version':'g1','rules':[{'dimension':'energy','direction':'low','guideline_id':'intro','language':'hi','native_text':'शुरुआत छोटी करें।','english_explanation':'Tighten the intro.','native_reviewer':'synthetic fixture reviewer'}]})
            report=segment_report(pred,d/'model.json',d/'clips.json',d/'rules.json',d/'internal.json')
            with self.assertRaisesRegex(ValueError,'approval'):creator_export(d/'internal.json',d/'creator.json')
            clip=report['clips'][0];flag=clip['flags'][0]
            content={k:flag.get(k) for k in ('id','original_transcript','native_suggestion','english_explanation','guideline_id')}
            content.update(start=clip['start'],end=clip['end'],video_sha256=report['video_sha256'],guideline_version=report['guideline_version'])
            flag['native_review']={'reviewer':'test human','language':'hi','approved':True,'content_sha256':fingerprint(content)}
            write_json(d/'internal.json',report);creator_export(d/'internal.json',d/'creator.json')
            flag['native_suggestion']='Changed after approval';write_json(d/'internal.json',report)
            with self.assertRaisesRegex(ValueError,'stale'):creator_export(d/'internal.json',d/'creator2.json')

    def test_transcript_quality_needs_native_references_not_confidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'samples.json'
            rows=[{'language':'hi','video_id':str(i),'native_reviewer':'fixture','reference_text':'नमस्ते दोस्त','hypothesis_text':'नमस्ते'} for i in range(10)]
            write_json(p,{'samples':rows});result=transcript_quality(p,Path(tmp)/'quality.json')
            self.assertEqual(result['hi']['wer'],.5)
            rows[0]['native_reviewer']='';write_json(p,{'samples':rows})
            with self.assertRaises(ValueError):transcript_quality(p,Path(tmp)/'bad.json')


if __name__=='__main__':unittest.main()
