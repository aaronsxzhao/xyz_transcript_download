"""Soft editorial guidance and private numeric diagnostics; never truncate output."""
import math
import re
from contextvars import ContextVar

PLAN = ContextVar('reading_budget_plan', default=None)
VERSION = 'focused-reading-v17'


def counts(text):
    return (len(re.findall(r'[\u3400-\u9fff]', text)),
            len(re.findall(r"[A-Za-z]+(?:['’][A-Za-z]+)?", text)))


def units(text, language):
    han, words = counts(text)
    return han if language == 'zh' else words


def make_plan(source, duration, language, style='detailed'):
    # Unknown/invalid duration falls back to speech length, never a guessed
    # playback timestamp. Other source languages have no English word budget.
    if language not in ('zh', 'en'):
        return {'language': language, 'style': style, 'estimated_duration': True}
    try:
        seconds = float(duration or 0)
    except (ValueError, TypeError):
        seconds = 0
    estimated = not math.isfinite(seconds) or seconds <= 0
    source_units = units(source, language)
    if estimated:
        seconds = source_units / (250 if language == 'zh' else 140) * 60
    minutes = seconds / 60
    # Anchors: 14m English -> 600-800 words; 67m Chinese -> 3000-3500
    # characters; 133m English -> 3000-4000 words. Interpolate softly.
    if language == 'zh':
        low, high = minutes * 3000 / 67, minutes * 3500 / 67
    elif minutes <= 14:
        low, high = minutes * 600 / 14, minutes * 800 / 14
    else:
        low, high = 600 + (minutes-14)*2400/119, 800 + (minutes-14)*3200/119
    # Detailed is the reference reading edition. Minimal requests less space,
    # but the same factual/qualification safeguards. Other styles change the
    # register or organization, not the importance of source evidence.
    if style == 'minimal':
        low, high = low * .65, high * .7
    # A sparse transcript must never be padded to match nominal media duration.
    low, high = min(low, source_units*.75), min(high, source_units*.9)
    return {'language': language, 'style': style, 'duration_seconds': round(seconds, 1),
            'estimated_duration': estimated, 'source_units': source_units,
            'target_low': max(0, round(low)), 'target_high': max(0, round(high)),
            'unit': 'Chinese characters' if language == 'zh' else 'English words'}


def guidance(source=None, *, share=None):
    plan = PLAN.get()
    if not plan or not plan.get('target_high'):
        return ''
    if share is None:
        share = min(1, units(source, plan['language']) / max(1, plan['source_units'])) if source is not None else 1
    share = min(1, max(0, share))
    low, high = (round(plan[key]*share) for key in ('target_low','target_high'))
    return (f'\nSOFT READING BUDGET: approximately {low}-{high} {plan["unit"]} '
            + ('for THIS supplied portion, not for every chunk. ' if share < .999 else 'for the whole note, including overview and takeaways. ')
            + 'Allocate space by informational value, not equal paragraphs per point. Preserve important independent arguments, '
            'reasoning, decisive evidence, disagreements, qualifications and meaningful closing reflections. '
            'Select informative examples; compress repetitive anecdotes and empty transitions. '
            'Do not pad a sparse source, truncate output, drop an essential condition, or invent claims to meet this soft range. '
            'Original quotes are separate evidence, not a way to duplicate the prose. Preserve the existing output schema and headings. '
            'Plan the available space BEFORE writing. Rank the central answers, decisive evidence and exceptions; '
            'use one explanation per argument, not one paragraph per source unit. '
            'Reserve at most 15 percent for overview and takeaways; spend the remainder on the arguments. '
            'Review your length before returning: remove repeated explanations and equivalent anecdotes first.\n')


def revision_guidance(sections, overview=''):
    """Share the original whole-note budget with every review/repair call."""
    plan=PLAN.get()
    text='\n'.join([overview,*[p['text'] for s in sections for p in s['paragraphs']]])
    if not plan or not plan.get('target_high'):
        return '\nPrefer the smallest informative addition; do not restate already covered explanations.\n'
    current=units(text,plan['language'])
    remaining=max(0,plan['target_high']-current)
    return guidance()+(
        f'\nThe existing note already contains about {current} {plan["unit"]}; '
        f'about {remaining} remain within the SOFT whole-note target. '
        'This is not a fresh allowance for each batch. When already above target, '
        'still preserve missing essential meaning, but omit setup already explained '
        'and combine related missing details. Do not pad or add incidental context.\n')


def _is_navigation(children):
    """A standalone fragment link is navigation, not prose containing a link."""
    inside = False
    linked = False
    for token in children:
        if token.type == 'link_open':
            if not (token.attrGet('href') or '').startswith('#'):
                return False
            inside = linked = True
        elif token.type == 'link_close':
            inside = False
        elif token.type in ('text', 'code_inline') and token.content.strip() and not inside:
            return False
    return linked


def visible_prose(markdown):
    """Count rendered prose, not link URLs, images, TOC or quoted evidence."""
    from markdown_it import MarkdownIt
    chunks=[]; quote_depth=0
    for token in MarkdownIt().parse(markdown or ''):
        if token.type == 'blockquote_open': quote_depth += 1
        elif token.type == 'blockquote_close': quote_depth -= 1
        elif token.type == 'inline' and not quote_depth:
            children=token.children or []
            # Standalone fragment links in a generated TOC repeat headings.
            if _is_navigation(children):
                continue
            chunks.extend(t.content for t in children if t.type in ('text','code_inline'))
        elif token.type in ('fence','code_block') and not quote_depth:
            chunks.append(token.content)
    return '\n'.join(chunks)


def estimated_minutes(prose, *, han_per_minute=350, words_per_minute=200):
    """Explicit reading rates; never use a reader's speed as an editing budget."""
    rates = (han_per_minute, words_per_minute)
    if any(not isinstance(rate, (int, float)) or isinstance(rate, bool)
           or not math.isfinite(rate) or rate <= 0 for rate in rates):
        raise ValueError('Reading rates must be positive finite numbers')
    han, words = counts(prose)
    return round(han / han_per_minute + words / words_per_minute, 2)


def diagnostics(result, source, plan):
    if isinstance(result, str):
        text = result
    else:
        text = '\n\n'.join([getattr(result,'overview',''),
            *[p.summary for p in getattr(result,'key_points',[])],
            *getattr(result,'takeaways',[])])
    prose = visible_prose(text)
    han, words = counts(prose)
    reading = estimated_minutes(prose)
    amount = units(prose, plan['language'])
    low, high = plan.get('target_low'), plan.get('target_high')
    paragraphs = [re.sub(r'\s+', ' ', p).strip().casefold() for p in prose.split('\n') if len(p.strip()) >= 60]
    return {**plan, 'output_han':han, 'output_words':words,
            'estimated_reading_minutes':reading,
            'reading_rate_basis':{'han_per_minute':350,'words_per_minute':200,'personalized':False},
            'exact_duplicate_paragraphs':len(paragraphs)-len(set(paragraphs)),
            'duplicate_metric_scope':'exact_text_only_not_semantic',
            'budget_status': ('not_applicable' if low is None else
                'below' if amount < low else 'above' if amount > high else 'within'),
            'advisory_only':True}
