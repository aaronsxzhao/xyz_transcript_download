"""Bounded synthetic provider checks; never emit generated text or credentials."""
import os
import re


def probe_summary_language():
    if not os.environ.get('GROQ_API_KEY'):
        return []
    from note_summarizer import NoteSummarizer
    from summary_errors import strip_delivery_notices
    engine = NoteSummarizer(api_key=os.environ['GROQ_API_KEY'],
        base_url='https://api.groq.com/openai/v1', model='openai/gpt-oss-120b')
    samples = {
        'en': 'The first prototype used a steel panel costing 40 dollars per unit. The second prototype cost 25 dollars, but only after ordering 100 units. These are prototype observations, not a forecast for mass production. We have not measured durability yet. The next test compares corrosion after three weeks. A cheaper panel is useful only if it passes that test.',
        'zh': '第一版原型使用钢板，每件成本四十美元。第二版每件二十五美元，但条件是一次订购一百件。这只是原型阶段的观察，不是量产成本预测。耐久性还没有测量。下一轮实验会比较三周后的腐蚀情况。便宜钢板只有通过这项测试才有用。',
    }
    reports = []
    for language, source in samples.items():
        report = {'library_profile':'probe_summary_' + language}
        try:
            note = engine._generate_single('Prototype review', source, 'detailed', ['summary']) or ''
            body = strip_delivery_notices(note)
            han = len(re.findall(r'[\u3400-\u9fff]', body))
            latin = len(re.findall(r'[A-Za-z]', body))
            matches = bool(body.strip()) and (han == 0 and latin > 50 if language == 'en' else han > 40)
            report.update(status=200 if matches else 500, language_matches=int(matches),
                          audit_completed=int(body == note.strip("\r\n")), response_bytes=len(note.encode()))
        except Exception:
            report.update(status=500, language_matches=0, audit_completed=0)
        reports.append(report)
    return reports
