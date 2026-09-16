"""Markdown report escapes upstream strings; it never embeds repository HTML."""
from datetime import datetime, timezone
from urllib.parse import urlparse

def safe_url(value):
    if not value: return None
    p=urlparse(value)
    return value if p.scheme=='https' and p.hostname in ('sourcecraft.dev','api.sourcecraft.tech') else None

def esc(s):
    s = 'Нет данных' if s is None else ('Да' if s is True else 'Нет' if s is False else s)
    return str(s).replace('\\','\\\\').replace('<','&lt;').replace('>','&gt;').replace('|','\\|').replace('[','\\[').replace(']','\\]').replace('\n',' ')

def markdown(slug, result):
    score = result['score'] if result['score'] is not None else 'Нет данных'
    lines=[f'# Repo Health: {esc(slug)}',f'Источник: https://sourcecraft.dev/{slug}',
           f"Дата: {datetime.fromtimestamp(result['analyzed_at'], timezone.utc).isoformat()}",
           f"Методика: {result['methodology']}",f'**Score: {score}/100**',
           f"Покрытие: {result['coverage']}%. Рейтинг: {'допущен' if result['rank_eligible'] else 'предварительная оценка'}.",
           f"SHA-256 нормализованных входов: `{result['input_sha256']}`",'']
    for c in result['categories']:
        lines += [f"## {c['name']}: {c['score'] if c['score'] is not None else 'Нет данных'}",f"Вес {c['weight']}%; покрытие {c['coverage']}%.",'', '| Метрика | Значение | Балл | Примечание |','|---|---|---|---|']
        for m in c['metrics']:
            lines.append(f"| {esc(m['title'])} | {esc(m['value'])} | {m['score'] if m['score'] is not None else 'Нет данных'} | {esc(m.get('note') or '')} |")
        lines += ['', 'Подтверждающие факты:']
        for m in c['metrics']:
            for f in m['facts']:
                url=safe_url(f.get('url'))
                lines.append('- '+esc(f['label'])+(f' — <{url}>' if url else ''))
        lines += ['']
    lines += ['## Рекомендации','']
    for r in result['recommendations']:
        lines += [f"### {r['priority']} · {esc(r['problem'])}",r['why'],r['action'],
                  f"Влияние: до +{r['delta_score']} Score; до +{r['delta_category']} по категории. {r['impact_note']}"]
        for f in r['facts']:
            lines.append('- '+esc(f['label']))
    lines += ['','## Диагностика источников','```json',__import__('json').dumps(result.get('diagnostics',{}),ensure_ascii=False,indent=2),'```',
              '', 'Пропуски не оцениваются нулём. Предварительные оценки не участвуют в основном рейтинге.',
              'Наличие README и текстовых инструкций не доказывает их корректность; TODO — прокси технического долга.']
    return '\n'.join(lines)
