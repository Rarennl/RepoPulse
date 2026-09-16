# Реальные отчёты SourceCraft

Сбор: 2026-09-16, анонимный HTTPS Git SourceCraft. Это реальные данные, не fixtures. Полные timestamp и SHA есть в JSON; исходники после анализа удалены.

| Репозиторий | Предварительный Score | Покрытие | Commit |
|---|---:|---:|---|
| [sourcecraft/documentation](https://sourcecraft.dev/sourcecraft/documentation) | 87.3 | 53% | 8337c7594aa6f8630b85b37d8376d7f247867e19 |
| [examples/self-hosted-worker](https://sourcecraft.dev/examples/self-hosted-worker) | 68.8 | 53% | 534f98ce21054dfcfac5ab94af5c135ed3cf20c2 |
| [sourcecraft/yc-ci-cd-serverless](https://sourcecraft.dev/sourcecraft/yc-ci-cd-serverless) | 48.3 | 33% | 91c652d7e3d44527c835d11ad3adff0dca9340df |

Все оценки предварительные, без допуска в основной рейтинг: Security неизвестна. Git дал факты о документации, CI config, активности и коде в пределах методики. Для CI runs, issues, releases и остальных REST-данных PAT не предоставлен. REST `/repos/sourcecraft/documentation` без токена вернул 401 Unauthorized.

`.md` — читаемые отчёты, `.json` — входы для `scripts/reproduce.py`. Высокая оценка при низком покрытии не подтверждает общую безопасность. Пропуски не заменены нулями или предположениями.
