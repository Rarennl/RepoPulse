# SourceCraft Repo Health

> Обновление интеграций v2: [актуальные изменения, установка и ограничения](UPDATE.md). Разделы ниже описывают исходную поставку v1; утверждения об отсутствии общего каталога и Security API заменены документом обновления. Исторические проверки и отчёты v1 сохранены.


Веб-сервис на Python/FastAPI с PostgreSQL, Redis, SQL-очередью, планировщиком, Git-анализом и русским интерфейсом. Исходный код и конфигурация запуска входят в этот репозиторий.

**Статус поставки: рабочая реализация ядра с ограничениями интеграции, не полная приёмка ТЗ.** Проверенная публичная API-схема SourceCraft не содержит AppSec и глобального списка репозиториев. Запрос к открытому репозиторию без PAT возвращает 401. OAuth-приложение Я ID и PAT не предоставлены. Поэтому live OAuth/REST/AppSec-анализ не подтверждён. Приложены три реальные Git-only оценки с явно указанными пропусками; это не полноценные оценки по всем шести категориям. Фальшивых баллов, уязвимостей и репозиториев нет. Подробно: [приёмка](docs/ACCEPTANCE.md), [ограничения](docs/LIMITATIONS.md).

## Запуск одной командой

Требования: Docker Engine и Docker Compose ≥2.24 (поддержка optional env_file), Linux/macOS/Windows с Docker, 4 CPU / 6 GB RAM / 10 GB диска для стартовой установки.

```bash
docker compose up --build -d --wait
```

Откройте http://localhost:8000. Без credentials сервис стартует с пустым рейтингом, а не с демо-данными. Swagger сервиса: http://localhost:8000/docs. PostgreSQL и Redis наружу не опубликованы.

Для реального сбора:

```bash
cp .env.example .env
# Заполните SOURCECRAFT_TOKEN и SOURCECRAFT_ORGS в .env
docker compose up --build -d --wait
```

Используйте отдельный PAT с минимальными правами для публичного сбора. В SOURCECRAFT_ORGS перечислите организации через запятую. Обход всех страниц их репозиториев автоматический. Не заявляется охват всей платформы.

После первого анализа включите «Включить предварительные оценки». До появления подтверждённого интерфейса AppSec основной рейтинг будет пуст по правилам полноты данных.

## Я ID и свои репозитории

1. Зарегистрируйте приложение Я ID, разрешите получение базового профиля (`login:info`).
2. Зарегистрируйте Redirect URI `http://localhost:8000/auth/callback` для локальной проверки; для внешнего запуска — точный HTTPS URL.
3. Заполните YANDEX_CLIENT_ID, YANDEX_CLIENT_SECRET, PUBLIC_ORIGIN, перезапустите Compose.
4. «Войти с Я ID» → «Мои репозитории» → подключить собственный PAT SourceCraft → указать организацию → выбрать репозиторий → «Запустить анализ».
5. Статус очереди обновляется автоматически. После завершения откроется детализация и выгрузка Markdown.

Я ID не считается разрешением на SourceCraft. Официальный проверенный способ REST-аутентификации — отдельный PAT. Не делается неподтверждённый обмен Я ID access_token на SourceCraft PAT. Пользователь видит только репозитории, которые SourceCraft разрешает его токену. Перечисление доступных организаций не представлено в опубликованном контракте: организация указывается явно.

Закрытые Git-исходники читаются через PAT владельца и временный askpass после проверки REST-доступа. Токен не помещается в clone URL или git config. Этот путь реализован, но live-проверка с закрытым репозиторием требует ваших credentials; при недоступности Git метрики остаются «Нет данных».

## Что входит

- Адаптер подтверждённых REST-методов, постраничное чтение, 20-секундные таймауты, 4 попытки с backoff/jitter, общий Redis rate-limit по credential.
- Опциональная read-only CLI-обёртка. CLI не включён в Docker: для локального использования установите официальную `src` и выполните `src init` в выделенном профиле. CLI не является автоматической заменой REST и не использует AI-режим.
- Шесть категорий в единой методике; Security live недоступна, а не имитирована.
- Входы, версия методики, SHA-256, категории, факты, рекомендации и история в SQL.
- SQL-очередь с SKIP LOCKED, heartbeat, lease fencing и ограничением повторов.
- Ежесуточное обновление активных, еженедельное неактивных проектов; ежедневный поиск в настроенных организациях.
- UI рейтинга, фильтр языка, сортировка, отчёт, история, настройки своего доступа; публичный JSON API, Markdown export.
- OAuth state + PKCE + привязка к браузеру, HttpOnly-сессии, CSRF, изоляция пользовательских отчётов, повторная проверка прав перед чтением и экспортом.

## Структура

```text
repo-health/
├── app/
│   ├── adapters/       # SourceCraft REST, CLI, потоковый Git
│   ├── static/         # UI: HTML, CSS, JavaScript без CDN
│   ├── collector.py    # Нормализация и источники фактов
│   ├── scoring.py      # Чистая воспроизводимая формула
│   ├── report.py       # Markdown
│   ├── main.py         # API, OAuth, ACL, UI
│   ├── db.py           # ORM + версия схемы
│   ├── queue.py        # SQL-очередь и leases
│   ├── worker.py       # Фоновый анализ
│   ├── scheduler.py    # Расписание, discovery, retention
│   └── config.py
├── contracts/sourcecraft.swagger.json
├── migrations/001_initial.sql
├── docs/               # Архитектура, методика, источники, приёмка
├── reports/            # Статус реальной проверки; live export отдельно
├── scripts/            # Проверка контракта, экспорт, воспроизведение
├── tests/              # Scoring, ACL, очередь, адаптер, нагрузочные границы
├── .sourcecraft/ci.yaml
├── .github/workflows/ci.yml
├── .env.example
├── requirements.txt    # Прямые зависимости
├── requirements.lock   # Зафиксированные транзитивные версии
├── Dockerfile
└── compose.yaml
```

## Приложенные реальные отчёты

В `reports/live/` находятся Markdown и JSON для `sourcecraft/documentation`, `examples/self-hosted-worker`, `sourcecraft/yc-ci-cd-serverless`. Это прямой анализ публичного Git SourceCraft, не fixtures. Coverage соответственно 53%, 53%, 33%; ни один не участвует в основном рейтинге без AppSec.

Повторный Git-only сбор без PAT:

```bash
python scripts/export_git_reports.py sourcecraft/documentation examples/self-hosted-worker sourcecraft/yc-ci-cd-serverless
```

## Проверки

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.lock
python -m pytest -q
python scripts/check_contract.py
```

```bash
curl --fail http://localhost:8000/health/ready
curl http://localhost:8000/api/leaderboard?partial=true
docker compose logs --tail=100 worker scheduler
```

Для трёх реальных публичных отчётов:

```bash
docker compose exec -w /tmp api sh -c 'PYTHONPATH=/app python /app/scripts/export_real_reports.py'
# Экспорт по умолчанию из organization=sourcecraft; можно задать REPORT_ORG.
# Файлы внутри контейнера /tmp/reports/live; скопировать:
docker compose cp api:/tmp/reports/live ./reports/live
```

JSON сохраняет входы для независимого воспроизведения:

```bash
python scripts/reproduce.py reports/live/ORGANIZATION--REPOSITORY.json
```

Сценарии раздела 8 ТЗ, включая сбой источника, повторный запуск, отзыв доступа и большой репозиторий: [docs/ACCEPTANCE.md](docs/ACCEPTANCE.md).

## Эксплуатация

```bash
# Worker реплики; задачи распределяет PostgreSQL
docker compose up -d --scale worker=3
# Остановка без удаления данных
docker compose down
```

Схема создаётся API/worker под advisory-lock. SQL `migrations/001_initial.sql` — эквивалент первоначальной схемы; не применять вручную поверх уже созданной БД. Дальнейшие изменения должны быть отдельными миграциями.

Для внешнего размещения: TLS reverse proxy, PUBLIC_ORIGIN=https://..., сильный POSTGRES_PASSWORD и отдельный TOKEN_ENCRYPTION_KEY. Секреты — через секрет-хранилище вашей инфраструктуры, не git. API по умолчанию слушает только loopback хоста. Не публикуйте PostgreSQL/Redis. Сохраните резервные копии PostgreSQL и ключа шифрования; потеря ключа потребует повторного подключения PAT. Redis содержит сессии, короткий metadata cache и ограничения частоты; SQL является источником истины для очереди и результатов.

Docker tags и Python версии закреплены; для строгой битовой воспроизводимости дополнительно закрепите digest базовых образов и apt snapshot после проверки вашей инфраструктурой. В текущей поставке нет утверждения о битовой идентичности сборок.

## Данные и внешние сервисы

Исходники не отправляются AI-провайдерам, в сторонние сканеры или на другие Git-платформы. Пользовательский репозиторий не исполняется. Git bare-копия временная, без checkout, удаляется в finally; /tmp — tmpfs и очищается при перезапуске контейнера. В БД сохраняются только метрики, идентификаторы/ссылки и небольшие факты, без текстов исходников, issues или секретов. Токены зашифрованы Fernet.

AI использовался при подготовке кода и документации данного решения. Runtime AI-summary не реализована. Это избегает передачи лицензированного или закрытого кода внешнему AI. Перед расширением сбора соблюдайте лицензии и правила доступа SourceCraft.
