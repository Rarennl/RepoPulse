# Приёмка и проверка сценариев

> Обновление интеграций v2: [актуальные изменения, установка и ограничения](../UPDATE.md). Разделы ниже описывают исходную поставку v1; утверждения об отсутствии общего каталога и Security API заменены документом обновления. Исторические проверки и отчёты v1 сохранены.


Дата: 2026-09-16. Синтетические fixtures находятся только в tests и не импортируются в production БД.

## Выполнено

- `python -m pytest -q`: 31 passed, одно deprecation warning AnyIO/Starlette.
- `python scripts/check_contract.py`: восемь методов сверены с официальной Swagger.
- `node --check app/static/app.js`: синтаксис корректен.
- 10000 tree entries / 100 API-страниц, поток реального локального Git fixture из 20000 коммитов.
- Sparse fixture 501 MiB: watchdog фиксирует превышение 500 MiB, не загружая файл в память.
- Scoring: null vs 0, coverage, renormalization, deterministic hash, отсутствие мутации, invalid numbers, AppSec источник/свежесть, counterfactual delta, likes вне формулы.
- ACL: чужой доступ к private detail/export, отзыв upstream прав, изоляция рейтинга, Origin+CSRF, OAuth state одноразовый и связан с браузером.
- Очередь: dedupe, expired lease reclaim, fencing старого worker.
- Три реальных публичных Git-only отчёта, воспроизведение по входам.

## Матрица

| Требование | Статус |
|---|---|
| Рейтинг, страница, Markdown, API | Реализованы; browser QA остаётся |
| Я ID и свой репозиторий | Код реализован; live проверка требует OAuth/PAT |
| Шесть категорий | Формулы/состояния есть; live AppSec не реализована |
| Воспроизводимость Score | Проверена |
| Нет данных не равны нулю | Проверено |
| Рекомендации и факты | Реализованы, delta проверена |
| Повторный фоновый анализ | Код и lease tests; Postgres concurrency не проверена |
| Большие репозитории | Синтетические границы; live 500 MiB не проверен |
| Закрытые данные | ACL tests прошли; нужны два живых аккаунта |
| Одна команда | Compose поставлен, daemon для проверки отсутствует |
| Масштабирование | Worker scaling, pagination, retry, budgets; ограничения описаны |
| Три реальных отчёта | Git-only, coverage 53/53/33% |
| Весь каталог | Не реализовано, configured organizations |

## 8.1. Просмотр открытого репозитория

1. В .env указать PAT публичного сбора и SOURCECRAFT_ORGS.
2. Выполнить `docker compose up --build -d --wait`.
3. Проверить `/health/ready`, журналы scheduler/worker; дождаться succeeded.
4. Открыть `/`, включить предварительные оценки, проверить язык/likes/даты.
5. Переключить язык, сортировки; открыть карточку, сверить категории, missing reasons, факты, рекомендации.
6. Скачать Markdown, сопоставить с UI. Без AppSec основной рейтинг должен оставаться пустым.

## 8.2. Анализ собственного репозитория

1. Зарегистрировать OAuth-приложение и точный callback, заполнить .env.
2. Войти с Я ID; после callback URL не содержит code, cookies HttpOnly, при HTTPS Secure.
3. Подключить PAT. Проверить отсутствие токена в ответах API/localStorage.
4. Указать организацию, выбрать repo, запустить; queued → running → succeeded.
5. Открыть отчёт и скачать Markdown. Для private проверить Git-доступ с PAT владельца.
6. Через 10 секунд повторить: новый analysis и история. Конкурирующие запросы при pending job должны возвращать тот же job.

## Приватность

Два аккаунта A/B и два PAT. Создать private report под A. Под B и анонимно запросить detail, report.md, job: 404/401, без анализа. Отозвать права A в SourceCraft: старый отчёт становится недоступен. Перевести public repo в private: публичные detail/export/leaderboard перестают выдавать его. Private issues внутри public repo не включаются в публичный анализ.

## Повторный запуск и сбои

- В тестовой БД установить repositories.last_attempt=0; scheduler поставит job в ближайшие 5 минут.
- `docker compose stop worker` / `docker compose start worker`: очередь сохраняется.
- Убить worker во время задачи: после lease 120 секунд новая реплика перехватывает; старый fencing token не может записать результат.
- На staging proxy вернуть 429/503: backoff/retry; 401/403 не становятся «пустым успешным» результатом.
- Неудачный job не меняет последний удачный analysis.
- `docker compose up -d --scale worker=3`: проверить конкуренцию в PostgreSQL.

## Большой репозиторий

Выбрать реальный SourceCraft repo ≥10000 файлов / ≥20000 коммитов / ≥500 MiB. Наблюдать RSS, tmpfs и число страниц. Проверить отсутствие checkout, исполнения кода, исходников в SQL. Превышение Git 1 GiB/600 секунд, blob 1 MiB или чтения 256 MiB должно дать missing, не 0. Обработка лимита корректна, но не считается полным покрытием большого repo.

## Повтор расчёта

```bash
python scripts/reproduce.py reports/live/sourcecraft--documentation.json
python scripts/reproduce.py reports/live/examples--self-hosted-worker.json
python scripts/reproduce.py reports/live/sourcecraft--yc-ci-cd-serverless.json
```

Ожидаются те же Score, coverage, категории, рекомендации и hash. Новый живой сбор может отличаться из-за времени и изменений источника.
