"""Pure deterministic scoring: input metrics + fixed analysis timestamp -> result."""
import hashlib
import json
import math
from decimal import Decimal, ROUND_HALF_UP

VERSION = '1.0.0'
CATEGORIES = {
 'docs': ('Документация',15), 'ci': ('CI/CD',15), 'security': ('Security',20),
 'activity': ('Активность',15), 'issues': ('Issues',15), 'code': ('Состояние кода',20),
}
# Local weights sum to 100 in every category. Popularity has no scoring input.
RULES = {
 'docs': [
 ('readme',25,'README','Добавьте содержательный README с назначением проекта.'),
 ('license',20,'Лицензия','Добавьте лицензию с понятными условиями использования.'),
 ('runbook',20,'Инструкция запуска','Опишите проверяемые команды установки и запуска.'),
 ('testguide',20,'Сборка и тесты','Документируйте команды сборки и тестирования.'),
 ('contributing',10,'CONTRIBUTING','Опишите порядок внесения изменений.'),
 ('codeowners',5,'CODEOWNERS','Назначьте владельцев областей кода.')],
 'ci': [('configured',20,'Конфигурация CI','Добавьте .sourcecraft/ci.yaml с проверками.'),
        ('success_rate',60,'Успешность CI','Разберите неуспешные запуски и устраните причины.'),
        ('stability',20,'Стабильность CI','Проверьте ухудшение успешности между двумя окнами.')],
 'security': [('sast',40,'SAST','Исправьте открытые уязвимости SAST, начиная с критических.'),
              ('sca',35,'SCA','Обновите уязвимые зависимости и повторите AppSec.'),
              ('secrets',25,'Secret scanning','Отзовите выявленные секреты и удалите их из истории.')],
 'activity': [('active_weeks',55,'Активные недели','Распределите содержательные изменения по времени.'),
              ('recency',35,'Давность коммита','Проверьте актуальность проекта и план сопровождения.'),
              ('contributors',10,'Авторы изменений','Расширьте круг сопровождающих и передачу знаний.')],
 'issues': [('response',45,'Первый ответ','Организуйте регулярный triage обращений.'),
            ('closure',30,'Время закрытия','Разберите задачи с длительным циклом обработки.'),
            ('stale',25,'Зависшие задачи','Проверьте старые открытые задачи и назначьте владельцев.')],
 'code': [('todo_density',45,'TODO/FIXME на 1000 строк','Разберите TODO/FIXME и заведите задачи.'),
          ('old_todo',35,'Давние TODO/FIXME','Проверьте незавершённые работы старше 180 дней.'),
          ('large_files',20,'Крупные исходные файлы','Разделите файлы свыше 1000 строк по ответственности.')],
}

def rounded(x):
    return float(Decimal(str(x)).quantize(Decimal('0.1'), rounding=ROUND_HALF_UP))

def metric(value, score, facts=None, note=None):
    if score is not None and (not math.isfinite(score) or not 0 <= score <= 100):
        raise ValueError('Metric score outside 0..100')
    return {'value':value, 'score':score, 'facts':facts or [], 'note':note}

def missing(reason): return metric(None, None, note=reason)

def calculate(metrics, analyzed_at):
    categories, recommendations = [], []
    numerator = denominator = coverage = 0.0
    for category, (label, weight) in CATEGORIES.items():
        items, local_num, local_den = [], 0.0, 0.0
        for key, local_weight, title, action in RULES[category]:
            item = dict(metrics.get(category, {}).get(key, missing('Источник не предоставил данные')))
            item.update(id=key, title=title, weight=local_weight)
            value = item['score']
            if value is not None:
                if not math.isfinite(value) or not 0 <= value <= 100:
                    raise ValueError('Invalid metric score')
                local_num += value * local_weight
                local_den += local_weight
            items.append(item)
        raw_score = local_num / local_den if local_den else None
        if raw_score is not None:
            numerator += raw_score * weight
            denominator += weight
        coverage += weight * local_den / 100
        categories.append({'id':category,'name':label,'weight':weight,'score':rounded(raw_score) if raw_score is not None else None,
                           'coverage':local_den,'metrics':items})
    total = rounded(numerator / denominator) if denominator else None
    for cat in categories:
        local_den = cat['coverage']
        for item in cat['metrics']:
            if item['score'] is None or item['score'] >= 80 or not item['facts']: continue
            delta_cat = (100 - item['score']) * item['weight'] / local_den
            delta_total = delta_cat * cat['weight'] / denominator
            priority = 'P0' if cat['id']=='security' and item['score']<=20 else ('P1' if delta_total>=5 else 'P2' if delta_total>=2 else 'P3')
            action = next(r[3] for r in RULES[cat['id']] if r[0]==item['id'])
            recommendations.append({'id':cat['id']+'.'+item['id'],'category':cat['name'],'priority':priority,
                'problem':f"{item['title']}: {item['score']}/100", 'why':'Этот показатель влияет на воспроизводимость, сопровождение или риск проекта.',
                'action':action,'facts':item['facts'],'delta_category':rounded(delta_cat),'delta_score':rounded(delta_total),
                'impact_note':'Верхняя оценка при доведении одного показателя до 100, остальных данных без изменений.'})
    recommendations.sort(key=lambda r:(r['priority'],-r['delta_score'],r['id']))
    known_security = next(c for c in categories if c['id']=='security')['coverage']==100
    canonical = json.dumps(metrics, ensure_ascii=False, sort_keys=True, separators=(',',':'), allow_nan=False)
    return {'methodology':VERSION,'analyzed_at':analyzed_at,'score':total,'coverage':rounded(coverage),
            'rank_eligible':coverage>=80 and known_security,'categories':categories,'recommendations':recommendations,
            'strengths':[c['name'] for c in categories if c['score'] is not None and c['score']>=80],
            'weaknesses':[c['name'] for c in categories if c['score'] is not None and c['score']<50],
            'input_sha256':hashlib.sha256(canonical.encode()).hexdigest(),'inputs':metrics}

def appsec_metrics(data, analyzed_at):
    """Only real completed SourceCraft AppSec scans can be normalized here.

    No public ingestion route: until a verified results API is available the
    collector calls this with unavailable. Unit-test fixtures are explicitly synthetic.
    """
    from datetime import datetime
    out = {}
    for kind in ('sast','sca','secrets'):
        scan = data.get(kind)
        if data.get('source') != 'SourceCraft AppSec' or not scan or scan.get('status')!='completed':
            out[kind] = missing(data.get('reason','Нет завершённого AppSec-сканирования'))
            continue
        scanned = datetime.fromisoformat(scan['completed_at'].replace('Z','+00:00')).timestamp()
        if not 0 <= analyzed_at-scanned <= 30*86400 or not scan.get('complete'):
            out[kind] = missing('Сканирование устарело или неполное'); continue
        penalties = {'critical':60,'high':25,'medium':8,'low':2,'info':0}
        findings = {f['id']:f for f in scan['findings']}.values()
        opened = [f for f in findings if f['status'] not in ('fixed','resolved','false_positive')]
        if any(f.get('severity') not in penalties for f in opened):
            out[kind] = missing('Неизвестная критичность AppSec'); continue
        score = max(0,100-sum(penalties[f['severity']] for f in opened))
        facts = [{'label':f['id']+' '+f['severity'], 'url':f.get('url')} for f in opened]
        facts = facts or [{'label':'Завершённое сканирование '+scan['id'],'url':scan.get('url')}]
        out[kind] = metric(len(opened),score,facts)
    return out
