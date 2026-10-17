"""Concise structured output; scores are computed, never supplied by the LLM."""


def build_evaluation(report):
    from studio_ocr import reading_text
    review=report.get('review',{})
    return {
        'narrative_breakdown':review.get('narrative_breakdown',dict.fromkeys(('hook','problem','product','resolution'),'Not assessed in this saved review.')),
        'detected_on_screen_elements':[{'text':reading_text(s['text']),'source_id':s['id'],'start':s['start'],'end':s['end'],
                                        'confidence':s.get('confidence'),'type':'recognized_screen_text_or_label'}
                                       for s in report.get('ocr',{}).get('sources',[])],
        'linguistic_review':review.get('linguistic_review',{'noted_slang':[], 'spoken_accuracy':'Not assessed in this saved review.'}),
        'performance_score':max(1,min(100,review['overall_score'])) if isinstance(review.get('overall_score'),(int,float)) else None,
        'score_basis':{'interpretation':'Estimated creative quality, not a prediction of views or virality.',
                       'rubric':[{'dimension':d['label'],'grade_out_of_4':d['grade'],'weight':d['weight'],'source_ids':d['source_ids']} for d in review.get('dimensions',[])],
                       'sensitivity_range':review.get('brand_review',review.get('estimate',{})).get('range')}
    }
