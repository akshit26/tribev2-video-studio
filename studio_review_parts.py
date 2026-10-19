"""Bounded, sequential review requests: summary, eight grades, then exact edits."""
import json
import re
import time


class ReviewOutputBudgetError(ValueError):
    """A complete JSON response could not fit in the bounded output request."""


def repeated_output(text):
    # Whole-word repetitions work with Indic Unicode without an English word list.
    return bool(re.search(r"(?<!\S)(\S+(?:\s+\S+){0,3})\s+(?:\1\s+){7,}\1(?:\s|$)", text))


def recognition_penalty(rationale):
    # A concession is not a deduction: "functional despite recognition noise"
    # caused valid positive assessments to fail both retries.
    rationale = re.sub(r'\b(?:despite|regardless of|irrespective of)\s+[^,.;!?]*(?:ocr|recognition|transcription)[^,.;!?]*',
                       lambda m: m[0] if re.search(r'reduc|weaken|lower|confus|hurt|penali|deduct',m[0],re.I) else '', rationale, flags=re.I)
    rationale = re.sub(r'\b(?:ocr|recognition|transcription)[^.;!?]*\b(?:not penalized|not penalised|not counted|not a creative defect|not a weakness)[^.;!?]*', '', rationale, flags=re.I)
    rationale = re.sub(r'\b(?:ocr|recognition|transcription)[^.;!?]*(?:does\s+not|doesn[\'’]t|did\s+not|is\s+not)\s+(?:undermine|affect|weaken|reduce|hurt|lower|penalize|penalise)[^.;!?]*', '', rationale, flags=re.I)
    return bool(re.search(r'(?:ocr|recognition|transcription).{0,90}(?:noise|noisy|error|fragment|misrecog|garbl|corrupt)|(?:noisy|fragmented|corrupted).{0,30}(?:overlay|ocr)',rationale,re.I|re.S))


def omit_recognition_faults(text):
    """Drop only sentences blaming the creative for recognition artifacts."""
    sentences = re.split(r'(?<=[.!?])\s+(?=[A-Z])', text)
    kept = [s for s in sentences if not (
        re.search(r'\b(?:ocr|recognition|transcription)\b', s, re.I) and
        re.search(r'\b(?:errors?|misspell\w*|misread\w*|typos?|inconsistent spelling|fragmented|noise|garbl\w*|corrupt\w*)\b', s, re.I))]
    return ' '.join(kept).strip()


def polish_unsupported_edits(raw, report):
    """Replace a few unsafe model edits with evidence-bound production directions."""
    dimensions = {row['key']: row for row in raw.get('dimensions', [])}
    all_sources = evidence(report)
    observed = ' '.join(s['text'] for s in all_sources).casefold()
    for edit in raw.get('edits', []):
        key = (edit.get('targets') or [None])[0]
        if key == 'credibility' and re.search(r'\b(?:unverified|unsupported|not backed|lack[s]? (?:visible )?(?:proof|evidence))\b',
                                               dimensions.get(key, {}).get('rationale', ''), re.I):
            if re.search(r'\b(?:reduce|kill|clear|cure|treat|prevent|repair|stop)\b', edit.get('replacement',''), re.I):
                edit.update(title='Remove or substantiate the efficacy claim', operation='replace',
                            instruction='Remove the numerical efficacy line unless the brand provides approved substantiation; keep only the verified ingredient name.',
                            replacement='[Brand-approved, verified benefit], or omit this claim.',
                            english_gloss='Use a verified approved benefit only; otherwise remove the claim.',
                            why='The original percentage and timing promise are not established by the available video.',
                            verify='Check approved claim wording and any required evidence before the final cut.')
        if key == 'cta':
            match = re.search(r'\bCOMMENT\s+\[([^]]+)\]\s+FOR\s+LINK\b', edit.get('replacement',''), re.I)
            if match and len(match[1].split()) > 2:
                candidate = match[1].split()[0].strip("'\".,")
                keyword = candidate if candidate.casefold() in observed else '[APPROVED KEYWORD]'
                edit.update(title='Add one testable next action', operation='insert',
                            instruction='End with one short comment keyword and specify the promised response; use this only if the brand can fulfil it.',
                            replacement=f"COMMENT '{keyword}' FOR LINK",
                            english_gloss=f"Ask viewers to comment {keyword} to receive the approved product link.",
                            why='The closing slogan names no concrete action or destination.',
                            verify=f"Test that commenting {keyword} returns the approved link; otherwise show the real purchase destination.")
        if key == 'visual' and re.search(r'\b(?:ocr|misread|spelling|typo|salicylicacid|plom)\b',
                                         edit.get('instruction','')+' '+edit.get('replacement',''),re.I):
            frames = [s['id'] for s in all_sources if s['kind']=='visual']
            if frames:
                edit.update(title='Add visual proof and shot variety', operation='insert',
                            source_ids=list(dict.fromkeys([frames[0], frames[len(frames)//2]])),
                            instruction='Break the repeated talking-head framing with a readable pack close-up and a genuine product-use shot.',
                            replacement='Add a short pack close-up, real shampoo application, and a clear end card with the verified product name.',
                            english_gloss='Show the actual product and its use; verify any caption against the source footage.',
                            why='Repeated framing and little demonstration weaken the visual payoff.',
                            verify='Watch the edited cut on a phone: confirm shot variety, legible labels, and genuine use footage.')


def burst_limits(observation):
    temperature = observation.get('temperature_c') if isinstance(observation, dict) else None
    if temperature is None: return 64, 16
    if temperature < 68: return 96, 32
    if temperature < 72: return 48, 16
    return 24, 8


def writer_burst_limits(observation):
    """Larger HTTP work units; the model batch size and thermal guards stay fixed."""
    temperature = observation.get('temperature_c') if isinstance(observation, dict) else None
    if temperature is None:
        return 64, 16
    if temperature < 68:
        return 192, 48
    if temperature < 72:
        return 128, 32
    return 64, 16


def check_edit_grounding(row, report):
    if recognition_penalty(row['why']+' '+row['instruction']):
        raise ValueError('Do not prescribe creative edits to fix OCR recognition errors. Address a weakness established by reliable speech or screen evidence; put extraction uncertainty in verification notes.')
    supplied = ' '.join(s['text'] for s in evidence(report)).casefold()
    # A new CTA is allowed, but an invented incentive is an unsupported promise.
    for phrase in re.findall(r'\bfree\s+(?:(?:\w+)\s+){0,2}(?:guide|gift|sample|trial|consultation|delivery|shipping)\b', row['replacement'], re.I):
        if ' '.join(phrase.casefold().split()) not in ' '.join(supplied.split()):
            raise ValueError('Do not invent a free guide, gift or other incentive. Use a plain next action with a brand-approved destination, or require the offer to be confirmed before writing it.')
    if re.search(r'\b(?:as stated|as labeled|as shown|printed|written).{0,20}\b(?:bottle|packaging)\b',row['replacement'],re.I):
        raise ValueError('OCR text alone does not establish that a benefit is printed on the bottle. Do not add that attribution; require claim verification against the approved brand brief.')


def check_edit_conflict(row, previous):
    if normalize_operation(row.get('operation')) != 'replace': return
    current=set(row.get('source_ids',[]))
    for earlier in previous:
        if normalize_operation(earlier.get('operation'))=='replace' and current.intersection(earlier.get('source_ids',[])):
            raise ValueError('An earlier edit already replaces this source span. Do not prescribe conflicting replacement scripts. Address the criterion with a different source span or a compatible cut, overlay, or audio direction.')


def contradicts_known_cta(text):
    text = re.sub(r'\b(?:not|never)\s+(?:confusing|unclear|messy|fragmented)\b','clear',text,flags=re.I)
    return bool(re.search(r'(?:confus\w*|unclear|messy|fragmented).{0,35}(?:\bcta\b|keyword|call to action)|(?:\bcta\b|keyword|call to action).{0,35}(?:confus\w*|unclear|messy|fragmented)|weak\s+(?:cta|call to action)\s+clarity',text,re.I))


def reconcile_summary_cta(result, known_ctas):
    """Replace contradicted descriptive claims with observed text, never grades."""
    if not known_ctas:return
    cta=known_ctas[0]
    fact=f"On-screen CTA: comment {cta['keyword']} for a link ({cta['source_id']})."
    for field in ('verdict','summary'):
        value=result.get(field)
        if not isinstance(value,str) or not contradicts_known_cta(value):continue
        result.setdefault('cta_grounding_corrections',{})[field]=value
        if field=='verdict':result[field]=fact
        else:
            sentences=re.split(r'(?<=[.!?])\s+(?=[A-Z])',value)
            result[field]=' '.join(fact if contradicts_known_cta(s) else s for s in sentences)

from studio_review import ANCHORS, RUBRIC, evidence, validate_review, normalize_operation, transcript_quality, normalize_absence_evidence


def cool_writer_burst_limits(observation):
    """New hybrid writer: more headroom for short temperature spikes."""
    temperature=observation.get('temperature_c',82)
    return (64,16) if temperature < 65 else (32,8)


def decoded_json(content):
    cleaned=content.strip()
    for marker in ('<|im_end|>','<|endoftext|>','</s>'):
        if cleaned.endswith(marker):cleaned=cleaned[:-len(marker)].rstrip()
    if cleaned.startswith('```json'):cleaned=cleaned[7:].strip()
    elif cleaned.startswith('```'):cleaned=cleaned[3:].strip()
    if cleaned.endswith('```'):cleaned=cleaned[:-3].rstrip()
    try:
        value=json.loads(cleaned)
        if isinstance(value,dict) and '\ufffd' not in json.dumps(value,ensure_ascii=False):return value
    except ValueError:pass
    return None


def generate_bursts(request, messages, token_budget, pause, label, context_tokens=4096, cache_state=None):
    """Bound both prompt evaluation and generation; cool between GPU bursts.

    Reuse only the current GPU slot, not the disabled host-memory prompt cache.
    Token IDs preserve multilingual byte sequences across continuation calls.
    """
    limits = (cool_writer_burst_limits if cache_state is not None and cache_state.get('cool_writer') else
              writer_burst_limits if cache_state is not None and cache_state.get('profile') == 'writer' else burst_limits)
    def completion(body):
        if cache_state is not None and cache_state.get('cool_writer'):
            time.sleep(.35)
            stats=cache_state.setdefault('timing',{})
            stats['writer_pacing_seconds']=stats.get('writer_pacing_seconds',0)+.35
        begun = time.monotonic()
        try:
            return request('/completion',body,timeout=120)
        finally:
            if cache_state is not None:
                stats = cache_state.setdefault('timing', {})
                stats['inference_request_seconds'] = stats.get('inference_request_seconds',0) + time.monotonic()-begun
                stats['completion_requests'] = stats.get('completion_requests',0)+1
    rendered = request("/apply-template", {"messages": messages})["prompt"]
    prompt_tokens = request("/tokenize", {"content": rendered, "add_special": False, "parse_special": True})["tokens"]
    if len(prompt_tokens) + token_budget + 32 > context_tokens:
        raise ValueError("This part exceeds the small GPU context. Split the video into shorter clips.")
    generated=list(cache_state.get('resume_tokens',[])) if cache_state is not None else []
    if generated:
        restored=decoded_json(request('/detokenize',{'tokens':generated})['content'])
        if restored is not None:return restored
    warm_tokens=prompt_tokens+generated
    previous = cache_state.get("tokens", []) if cache_state is not None else []
    common = 0
    for old, new in zip(previous, warm_tokens):
        if old != new:
            break
        common += 1
    # Reuse the common evidence prefix already in this GPU slot. This avoids
    # repeatedly shrinking and refilling it for every criterion and edit.
    end = common
    while end < len(warm_tokens):
        observation = pause(f"{label}: reading evidence ({round(100 * end / len(warm_tokens))}%)")
        prefill, _ = limits(observation)
        end = min(end + prefill, len(warm_tokens))
        result = completion({"prompt": warm_tokens[:end], "n_predict": 0,
                         "cache_prompt": True, "id_slot": 0})
        if result.get("truncated"):
            raise ValueError("GPU prompt context was truncated")
    content = ""
    while len(generated) < token_budget:
        observation = pause(f"{label}: drafting in short bursts")
        _, output_burst = limits(observation)
        sampling = cache_state.get('sampling', {}) if cache_state is not None else {}
        result = completion({"prompt": prompt_tokens + generated,
                         "n_predict": min(output_burst, token_budget - len(generated)), "temperature": sampling.get('temperature', 0),
                         "top_p": sampling.get('top_p', .95),
                         "repeat_penalty": 1.12, "repeat_last_n": 256,
                         "seed": sampling.get('seed', 42), "cache_prompt": True, "id_slot": 0, "return_tokens": True})
        if result.get("truncated"):
            raise ValueError("GPU output context was truncated")
        generated.extend(result.get("tokens", []))
        # A burst boundary can split the UTF-8 bytes of an Indic character.
        # Concatenating separately decoded responses preserves U+FFFD corruption.
        # Decode the complete token sequence each time instead.
        content = request("/detokenize", {"tokens": generated})["content"]
        if cache_state is not None:
            cache_state["last_output"] = content
            if cache_state.get('save_partial'):cache_state['save_partial'](generated)
        if repeated_output(content):
            raise ValueError("Repeated text detected. Write concise editing directions in English if native wording is uncertain; do not imitate corrupted transcript text.")
        if cache_state is not None:
            cache_state["tokens"] = prompt_tokens + generated
        value=decoded_json(content)
        if value is not None:return value
        if result.get("stop_type") != "limit" or not result.get("tokens"):
            raise ValueError("GPU review part did not return a complete JSON object")
    raise ReviewOutputBudgetError("Review part exceeded its output budget; incomplete text was rejected")


def evidence_chunks(sources, count_tokens, limit=900):
    """Read every source, including unusually long single transcript segments."""
    chunks, current = [], []
    for source in sources:
        remaining = source["text"]
        while remaining:
            if count_tokens(json.dumps([dict(source, text=remaining)], ensure_ascii=False)) <= limit:
                piece, remaining = remaining, ""
            else:
                low, high = 1, len(remaining)
                while low < high:
                    mid = (low + high + 1) // 2
                    if count_tokens(json.dumps([dict(source, text=remaining[:mid])], ensure_ascii=False)) <= limit:
                        low = mid
                    else:
                        high = mid - 1
                piece, remaining = remaining[:low], remaining[low:]
                if count_tokens(json.dumps([dict(source, text=piece)], ensure_ascii=False)) > limit:
                    raise ValueError("Transcript metadata exceeds the section budget")
            row = dict(source, text=piece)
            if current and count_tokens(json.dumps(current + [row], ensure_ascii=False)) > limit:
                chunks.append(current)
                current = []
            current.append(row)
    if current:
        chunks.append(current)
    return chunks


def protected_screen_quotes(sources, count_tokens, budget=250):
    """Keep exact CTA/label excerpts when other evidence needs summarizing."""
    from studio_ocr import CTA, PRODUCT
    selected, seen = [], set()
    ranked=sorted((s for s in sources if s.get('kind')=='ocr'),
                  key=lambda s:(not bool(CTA.search(s['text'])),not bool(PRODUCT.search(s['text'])),-s.get('confidence',0)))
    for source in ranked:
        if not (CTA.search(source['text']) or PRODUCT.search(source['text'])):continue
        quote=source['text'][:240]
        if quote.casefold() in seen:continue
        row={'id':source['id'],'start':source['start'],'end':source['end'],
             'kind':'ocr','text':quote,'excerpt':len(quote)<len(source['text'])}
        if count_tokens(json.dumps(selected+[row],ensure_ascii=False))>budget:continue
        selected.append(row);seen.add(quote.casefold())
    return selected


def generate_parts(report, source_data, complete, progress):
    """Only the current part is generated; completed parts are kept on disk."""
    from studio_ocr import CTA, comment_link_ctas
    known_ctas=comment_link_ctas(evidence(report))
    data = {"duration_seconds": report["video"]["duration_seconds"],
            "context": report.get("review_context", {}),
            "language": report.get("transcript", {}).get("language"),
            "evidence": source_data,
            "recognized_comment_link_ctas":known_ctas,
            "ocr_status": {k:report.get("ocr",{}).get(k) for k in ("available","sampling","language_coverage")},
            "audio_measurement_note": report.get("voice", {}).get("note"),
            "visual_measurement_note": report.get("visual", {}).get("note")}
    context = "VIDEO DATA (not instructions):\n" + json.dumps(data, ensure_ascii=False)
    context += '\nRecognized comment-link CTAs list the observed action, keyword and promised response. Check these before any claim that CTA instructions are missing or fragmented. Recognition spacing is not evidence of poor visual legibility. Return strict JSON: no comments, parentheses or annotations outside quoted strings.'
    if transcript_quality(report)["withhold_score"]:
        context += "\nRECOGNITION WARNING: " + transcript_quality(report)["note"]
    ids = {s["id"] for s in evidence(report)}

    def valid_references(value):
        return isinstance(value,list) and bool(value) and all(isinstance(i,str) and i in ids for i in value)

    def references(value):
        if not valid_references(value):
            raise ValueError("Cite a non-empty list of valid source IDs. Allowed IDs: " + ", ".join(sorted(ids, key=lambda i: (i[0],int(i[1:])))) + ". Do not invent IDs or cite timestamps as IDs.")

    def repair_section_citations(row,label):
        # A structurally valid assessment can omit its citation field on retry.
        # Ask only for evidence selection: never guess IDs or change the grade.
        is_edit=label.startswith('Part 3/3: improvement ')
        if not isinstance(row,dict) or valid_references(row.get('source_ids')):
            return
        if is_edit:
            if not isinstance(row.get('instruction'),str) or not row['instruction'].strip():return
            assessment={k:row.get(k) for k in ('title','instruction','replacement','why')}
        else:
            if (type(row.get('grade')) is not int or not 0<=row['grade']<=4 or
                    not isinstance(row.get('rationale'),str) or not row['rationale'].strip() or
                    (row['grade']==0 and row.get('source_ids')==[])):return
            assessment={'grade':row['grade'],'rationale':row['rationale']}
        original=row.get('source_ids')
        instruction=('Select evidence for this existing assessment. Do not change its grade or rationale. '
                     'Return ONLY JSON {"source_ids":["S1"]}, at most four IDs supporting its actual claims. '
                     'Select only IDs from ALLOWED_IDS below; no ranges, invented IDs or timestamps. '
                     'If no supplied source supports it, return {"source_ids":[]} rather than inventing support. '
                     'ASSESSMENT: '+json.dumps(assessment,ensure_ascii=False)+
                     '\nALLOWED_IDS: '+json.dumps(sorted(ids)))
        if is_edit:
            instruction+='\nThis is a PROPOSED EDIT. Select the existing source span anchoring the cut/insertion/replacement. Proposed replacement words are future material, not a quote from the video. Keep all edit wording unchanged.'
        instruction=instruction.replace('["S1"]',json.dumps([evidence(report)[0]['id']]))
        problem=''
        for attempt in range(2):
            correction='' if not problem else '\nCorrect the citation selection: '+problem
            candidate=complete(context+'\n'+instruction+correction,200,label+' / citation selection')
            try:
                selected=candidate.get('source_ids') if isinstance(candidate,dict) else None
                references(selected)
                row['source_ids']=list(dict.fromkeys(selected))
                row['citation_repair']={'original_source_ids':original,'method':'local evidence selection; assessment and edit wording unchanged'}
                return
            except ValueError as exc:
                problem=str(exc)
                # No supported evidence is a legitimate refusal, not a reason
                # to manufacture references or borrow a prior attempt's IDs.
                if selected==[]:break
        raise ValueError('Citation repair could not establish valid evidence. '+problem)

    def required_text(row, fields):
        if not isinstance(row, dict) or any(not isinstance(row.get(f), str) or not row[f].strip() for f in fields):
            raise ValueError("Missing required text fields: " + ", ".join(fields))

    def part(label, instruction, tokens, check, fraction):
        # OCR-only videos have no S1; examples must use a real supplied ID too.
        instruction=instruction.replace('["S1"]',json.dumps([evidence(report)[0]['id']]))
        progress(fraction, label)
        for attempt in range(2):
            suffix = "" if attempt == 0 else "\nCorrect the previous schema error: " + problem
            try:
                result = complete(context + "\n" + instruction + suffix, tokens, label)
                if label.startswith(('Part 2/3: rating ','Part 3/3: improvement ')):
                    repair_section_citations(result,label)
                check(result)
                return result
            except (ValueError, TypeError, KeyError) as exc:
                problem = str(exc)
        raise ValueError(f"{label} failed validation: {problem}")

    def check_summary(result):
        required_text(result, ["summary", "verdict", "content_language"])
        reconcile_summary_cta(result,known_ctas)
        cleaned = omit_recognition_faults(result['summary'])
        if cleaned and cleaned != result['summary']:
            result['summary'] = cleaned
            result['summary_recognition_correction'] = True
        if re.search(r'\b(ocr|recognition|transcription)\b',result['verdict'],re.I):
            raise ValueError('The verdict must judge the creative, not the extraction system. OCR/transcription noise belongs in uncertainties, never as a creative weakness in the verdict or summary. Give an evidence-based creative verdict.')
        if known_ctas and contradicts_known_cta(result['verdict']+' '+result['summary']):
            raise ValueError('The recognized CTA has an explicit comment action, exact keyword and link response. Do not call that keyword or instruction confusing, fragmented or messy based on OCR formatting. State any other supported weakness instead; actual visual legibility is unverified.')
        actionable = any(CTA.search(s['text']) for s in evidence(report) if s['kind'] in {'speech','ocr'})
        if not actionable and re.search(r'\b(?:strong|clear|effective|consistent)\s+(?:closing\s+)?(?:cta|call.to.action)\b',
                                        result['verdict']+' '+result['summary'], re.I):
            raise ValueError('A slogan is not a viewer action. Do not praise the CTA unless speech or an overlay names a real next step.')
        if not isinstance(result.get("strengths"), list) or not 1 <= len(result["strengths"]) <= 5:
            raise ValueError("Provide 1-5 evidence-based strengths")
        for row in result["strengths"]:
            required_text(row, ["title", "detail"])
            references(row.get("source_ids"))
            if not actionable and re.search(r'\b(?:cta|call.to.action)\b',row['title']+' '+row['detail'],re.I):
                raise ValueError('Do not list a slogan as a CTA strength without an observable viewer action.')
        if not isinstance(result.get("uncertainties"), list):
            raise ValueError("uncertainties must be a list")
        if report.get("ocr"):
            required_text(result.get("narrative_breakdown",{}),["hook","problem","product","resolution"])
            required_text(result.get("linguistic_review",{}),["spoken_accuracy"])
            if not isinstance(result["linguistic_review"].get("noted_slang"),list):
                raise ValueError("linguistic_review.noted_slang must be a list; include only observed expressions")

    raw = part("Part 1/3: detailed summary and best moments",
               'Return one COMPLETE, SHORT JSON object with exactly these fields: '
               '{"summary":"Audience, message, progression, strongest element and main weakness in at most 45 words",'
               '"verdict":"Creative verdict under 8 words","content_language":"Language code",'
               '"strengths":[{"title":"Real strength","detail":"Why, under 15 words","source_ids":["S1"]}],'
               '"uncertainties":["One evidence limitation"],'
               '"narrative_breakdown":{"hook":"One short sentence","problem":"One short sentence","product":"One short sentence","resolution":"One short sentence"},'
               '"linguistic_review":{"noted_slang":[],"spoken_accuracy":"Short assessment of speech intelligibility"}}. '
               'Use real source IDs in the summary and strength. Give ONE real strength. A slogan is not a CTA; '
               'do not praise an absent action. Do not infer visual appeal or vocal energy from text. '
               'Keep OCR errors out of the summary, verdict and strengths; they are evidence limitations only. '
               'Name an actual creative weakness supported by source evidence. Stop immediately after the final }.',
               650, check_summary, .28)
    raw["dimensions"] = []
    def check_dimension(row, key):
            required_text(row, ["rationale"])
            normalize_absence_evidence(row, ids)
            references(row.get("source_ids"))
            if type(row.get("grade")) is not int or not 0 <= row["grade"] <= 4:
                raise ValueError("grade must be an integer 0-4")
            cleaned = omit_recognition_faults(row['rationale'])
            if cleaned and cleaned != row['rationale']:
                row['rationale'] = cleaned
                row['recognition_correction'] = True
            if row['grade']<4 and recognition_penalty(row['rationale']):
                raise ValueError('Recognition noise cannot justify losing creative points. Reassess using clear speech and trusted OCR only. Name a real creative strength/weakness, not fragmented OCR or labeling errors inferred from misrecognition. Keep extraction limitations out of the grading rationale; do not automatically raise the grade.')
            if key == 'cta':
                actionable = any(CTA.search(s['text']) for s in evidence(report) if s['kind'] in {'speech','ocr'})
                if not actionable and row['grade'] > 1:
                    raise ValueError('No observed speech or overlay names a viewer action and destination. A slogan is not a CTA; grade at most 1 for an implied invitation, or 0 if absent. Cite the closing evidence.')
            if key=='cta' and known_ctas:
                if contradicts_known_cta(row['rationale']):
                    raise ValueError('The action, keyword and promised link are explicit in the recognized CTA. Judge remaining relevance or friction using evidence; do not invent keyword ambiguity from OCR spacing.')
                if not any(c['source_id'] in row['source_ids'] for c in known_ctas):
                    raise ValueError('A CTA assessment must cite the observed closing overlay. Valid CTA source IDs: '+', '.join(c['source_id'] for c in known_ctas))
            for dimension_kind, prefix in (('voice','A'),('visual','V')):
                if key != dimension_kind:
                    continue
                available = [s['id'] for s in evidence(report) if s['id'].startswith(prefix)]
                if available and not any(i in row['source_ids'] for i in available):
                    raise ValueError(f'{dimension_kind} must cite its direct {prefix} evidence, not only speech/OCR.')
                if not available and row['grade'] > 2:
                    raise ValueError(f'{dimension_kind} cannot receive a strong grade without direct sampled evidence.')
                if key == 'visual' and available and report['video']['duration_seconds'] > 15 and row['grade'] >= 3:
                    if len(set(row['source_ids']).intersection(available)) < 2:
                        raise ValueError('A strong visual grade needs at least two sampled frames from different parts of the video.')

    def check_dimension_batch(value):
        rows=value.get('dimensions') if isinstance(value,dict) else None
        expected=[r[0] for r in RUBRIC]
        if not isinstance(rows,list) or len(rows)!=len(expected) or [r.get('key') for r in rows]!=expected:
            raise ValueError('Return every dimension in the supplied key order: '+', '.join(expected))

    rubric_data=[{'key':key,'label':label,'criterion':description} for key,label,_,description in RUBRIC]
    batch_rows = {}
    try:
        batch=part("Part 2/3: all ratings",
                   'Assess ALL rubric dimensions in this exact order: '+json.dumps(rubric_data,ensure_ascii=False)+'\n'+ANCHORS+'\nReturn JSON {"dimensions":[{"key":"hook","grade":2,"rationale":"At most 34 words using decisive creative evidence","source_ids":["S1"]}]}. Include exactly one row per supplied key, at most FOUR valid source IDs each. Cite A for voice and V for visuals. Judge what the source actually supports: readable OCR does not establish visual appeal, and a transcript does not establish vocal energy. Judge recognition uncertainty separately from creative quality. Do not inflate grades.',
                   1300,check_dimension_batch,.40)
        for row,(key,label,_,_) in zip(batch['dimensions'], RUBRIC):
            try:
                repair_section_citations(row,f"Part 2/3: rating {label}")
                check_dimension(row,key)
                batch_rows[key]=row
            except (ValueError,TypeError,KeyError):
                # Preserve valid dimensions. One unsupported grade must not
                # trigger regeneration of the whole 8-row response.
                pass
    except ValueError:
        pass
    for index, (key, label, weight, description) in enumerate(RUBRIC):
        if key in batch_rows:
            raw['dimensions'].append(batch_rows[key])
            continue
        # Regenerate only missing or unsupported criteria.
        row = part(f"Part 2/3: rating {label} ({index + 1}/{len(RUBRIC)})",
                   f'Assess only {label}: {description}\n{ANCHORS}\nCite direct A evidence for voice or V evidence for visuals when available.\n'
                   'Return JSON {"grade":2,"rationale":"ONE paragraph of at most 42 words: the decisive evidence and reason for this grade","source_ids":["S1"]}. Cite at most FOUR supplied IDs. No essay, repeated argument or full transcript quotations. Recognition noise is uncertainty, not a creative defect. Do not inflate the grade.',
                   280, lambda value,k=key:check_dimension(value,k), .40 + index * .045)
        row["key"] = key
        raw["dimensions"].append(row)
    # Each weak criterion receives its own edit. For strong videos retain at
    # least three optional refinements without claiming a guaranteed increase.
    weights = {r[0]: r[2] for r in RUBRIC}
    ranked = sorted(raw["dimensions"], key=lambda r: max(0, 3 - r["grade"]) * weights[r["key"]], reverse=True)
    selected = [r for r in ranked if r["grade"] < 3]
    selected += [r for r in ranked if r not in selected][:max(0, 3 - len(selected))]
    selected = selected[:3]
    if raw.get('summary_recognition_correction') or re.search(r'\b(?:strong|clear)\s+(?:call|cta)\b',raw.get('summary',''),re.I) and not any(
            CTA.search(s['text']) for s in evidence(report) if s['kind'] in {'speech','ocr'}):
        weakest = next((r for r in ranked if r['grade'] < 3), None)
        if weakest:
            sentences = re.split(r'(?<=[.!?])\s+(?=[A-Z])', raw['summary'])
            clean_intro = ' '.join(s for s in sentences if not re.search(r'\b(?:ocr|recognition|transcription|strong call|clear cta)\b',s,re.I)).strip()
            concern = re.split(r'(?<=[.!?])\s+(?=[A-Z])', weakest['rationale'])[0].strip()
            raw['summary'] = (clean_intro + ' Main weakness: ' + concern).strip()[:600]
            label = next(label for key,label,_,_ in RUBRIC if key == weakest['key'])
            raw['verdict'] = 'Revise ' + label.lower()
    raw["edits"] = []
    for index, dimension in enumerate(selected):
        key = dimension["key"]
        def check_edit(row):
            required_text(row, ["title", "operation", "instruction", "replacement", "english_gloss", "why", "verify"])
            check_edit_grounding(row, report)
            references(row.get("source_ids"))
            row["operation"] = normalize_operation(row["operation"])
            if row["operation"] not in {"cut", "replace", "insert", "move", "overlay", "audio"}:
                raise ValueError("operation must be cut, replace, insert, move, overlay, or audio")
            check_edit_conflict(row, raw['edits'])
        prior = [{k: r[k] for k in ("title", "targets", "operation", "source_ids", "instruction")}
                 for r in raw["edits"]]
        try:
            edit = part(f"Part 3/3: improvement {index + 1}/{len(selected)} ({key})",
                    "Current criterion assessment: " + json.dumps(dimension, ensure_ascii=False) +
                    "\nPrevious edits (avoid duplication): " + json.dumps(prior, ensure_ascii=False) +
                    '\nGive ONE exact edit addressing this criterion, aiming for strong 3/4 or better, without predicting a new score. '
                    'operation MUST be one of: cut, replace, insert, move, overlay, audio. Use insert for adding new material. '
                    'Use natural original-language replacement wording with an English gloss. Keep a hook under 12 spoken words and a CTA under 16; shorten the source, not lengthen it. '
                    'Never guess a corrected ingredient, invent a personal result, or write unverified before/after claims. For uncertain claims, direct the editor to verify the label and omit unsupported wording; use [verified ingredient] placeholders if needed. '
                    'Do not repeat an earlier edit or assign conflicting replacements to the same source span. Keep the title under 8 words, instruction under 25, why and verify under 18 each. Return JSON '
                    '{"title":"Edit title","operation":"replace","source_ids":["S1"],'
                    '"instruction":"Concrete action tied to source evidence","replacement":"Exact words or cut/move direction",'
                    '"english_gloss":"English meaning","why":"Reason","verify":"Observable acceptance check"}.',
                    500, check_edit, .70 + index * .045)
        except ValueError:
            source = evidence(report)[-1 if key == "cta" else 0]
            if key not in {"cta", "hook"}:
                source = next(s for s in evidence(report) if s["id"] == dimension["source_ids"][0])
            directions = {
                "cta": "Check the closing speech with a fluent editor. If no clear next action is present, append a short closing shot naming one action, what the viewer receives, and where it happens. Keep an existing clear CTA.",
                "hook": "Check the opening with a fluent editor. Cut repetitive setup only after verifying the audio, and open with the specific viewer problem or payoff already supported by the video.",
                "clarity": "Verify the central product message with a fluent editor. Keep one concrete supported benefit; correct captions against the spoken audio and product brief.",
                "structure": "Review this source span in context. Remove repeated setup only after checking the audio, and order the remaining shots as problem, demonstration, payoff and next action.",
                "credibility": "Verify this claim and ingredient names against the product label or brand brief. Remove unsupported promises; use an actual demonstration without presenting it as clinical proof.",
                "emotion": "Check the intended feeling with a fluent editor. Emphasize an existing relatable problem or visible payoff without adding an invented personal result.",
                "voice": "Review the original audio with a fluent editor. Tighten long pauses, balance speech against music and record the key payoff with clearer vocal emphasis.",
                "visual": "Replace repeated static framing with a close product shot and a genuine application or result shot where available; enlarge low-visibility text and verify it on a phone."
            }
            edit = {"title": "Fluent-editor check: " + key, "operation": "audio", "source_ids": [source["id"]],
                    "instruction": directions[key], "replacement": "Native-language copy could not be generated reliably. Use the editing directions above; a fluent editor must supply and time any new spoken line.",
                    "english_gloss": "Editing directions only; no verified native-language replacement was generated.",
                    "why": "This criterion needs attention, but repeated or invalid generated text was rejected.",
                    "verify": "Confirm the actual speech, claims and timing with a fluent reviewer before applying this edit."}
            raw["uncertainties"].append(f"The {key} rewrite could not be generated reliably after two attempts. Its edit is a clearly marked fluent-editor checklist, not verified replacement copy.")
        edit["targets"] = [key]
        raw["edits"].append(edit)
    polish_unsupported_edits(raw, report)
    review=validate_review(raw, report)
    for key in ("narrative_breakdown","linguistic_review"):
        if key in raw:review[key]=raw[key]
    return raw, review
