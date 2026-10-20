"""Small, attributed reference library; original samples are not transcripts."""
import json
import random
import re
from pathlib import Path
from studio_script_language import normalize_language

ROOT = Path(__file__).resolve().parent
NICHES = {"auto":"Detect from brief", "skincare":"Skincare / haircare", "fashion":"Fashion", "arcade":"Arcade", "food_drinks":"Food and drinks", "fmcg":"FMCG / household"}


def catalog():
    return json.loads((ROOT/'script_examples.json').read_text(encoding='utf-8'))


def niche_for(brief):
    selected = brief.get('niche','auto')
    if selected in NICHES and selected != 'auto':
        return selected
    content = ' '.join(str(brief.get(k,'')) for k in ('topic','facts')).casefold()
    for niche, pattern in [
        ('arcade',r'arcade|gaming|pinball|claw|गेम|आर्केड'),
        ('skincare',r'skin|serum|sunscreen|moisturi|shampoo|dandruff|haircare|cleanser|त्वचा|शैंपू|सनस्क्रीन|बालों'),
        ('fashion',r'fashion|outfit|shirt|jeans|dress|clothing|shoe|kurta|saree|कपड़|कुर्ता|साड़ी|जूते'),
        ('food_drinks',r'food|drink|snack|tea|coffee|soda|juice|biscuit|chocolate|cucumber|pizza|burger|खाना|चाय|कॉफी|बिस्कुट')]:
        if re.search(pattern,content):
            return niche
    return 'fmcg'


def selected_examples(brief):
    rows = [r for r in catalog()['examples'] if r['niche']==niche_for(brief)]
    random.Random(brief.get('generation_seed',42)).shuffle(rows)
    language = normalize_language(brief.get('language','English'))
    # Never feed English copy into a Hindi prompt as a translation template.
    if language == 'Hindi (Roman)':
        return [{"id":r['id'],"pattern":r['pattern'],"avoid":r['avoid']} for r in rows[:2]]
    return [{"id":r['id'],"pattern":r['pattern'],"avoid":r['avoid'],
             "original_example":r['scripts'].get(language,'')} for r in rows[:2]]


def example_guidance(brief):
    return ' Apply the supplied learned mechanism rules conditionally. Generate a fresh premise and fresh words for this product. No script templates, copied transcript wording or reusable fill-in-the-blank hooks. Research mechanisms are hypotheses, not proof of causal virality or product efficacy. '
