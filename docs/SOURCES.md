# Подтверждённые источники и контракты

> Обновление интеграций v2: [актуальные изменения, установка и ограничения](../UPDATE.md). Разделы ниже описывают исходную поставку v1; утверждения об отсутствии общего каталога и Security API заменены документом обновления. Исторические проверки и отчёты v1 сохранены.


Проверка: 16 сентября 2026. Официальная Swagger сохранена в `contracts/sourcecraft.swagger.json`; не заменяется выдуманным API.

- Документация: https://sourcecraft.dev/portal/docs/ru/
- REST-аутентификация: https://sourcecraft.dev/portal/docs/ru/sourcecraft/operations/api-start
- API UI: https://api.sourcecraft.tech/docs/index.html
- Фактический JSON, указанный в HTML API UI: https://api.sourcecraft.tech/docs/sourcecraft.swagger.json
- CLI: https://sourcecraft.dev/portal/docs/ru/sourcecraft/operations/cli-quickstart
- Git: https://sourcecraft.dev/portal/docs/ru/sourcecraft/operations/repo-clone
- Я ID OAuth: https://yandex.ru/dev/id/doc/ru/codes/code-url
- Каталог: https://sourcecraft.dev/find/repositories (динамический UI, не подтверждённый REST endpoint).

| Данные | Проверенный метод |
|---|---|
| Профиль токена | GET /user |
| Репозиторий | GET /repos/{org_slug}/{repo_slug} |
| Репозитории организации | GET /orgs/{org_slug}/repos |
| Дерево | GET /repos/{org_slug}/{repo_slug}/trees |
| CI | GET /repos/{org_slug}/{repo_slug}/cicd/runs |
| Issues | GET /repos/{org_slug}/{repo_slug}/issues |
| Ответы | GET /repos/{org_slug}/{repo_slug}/issues/{issue_slug}/comments |
| Зависимости issues | GET /repos/{org_slug}/{repo_slug}/issues/{issue_slug}/issue_links |
| MR / PR | GET /repos/{org_slug}/{repo_slug}/pulls |
| Contributors | GET /repos/{org_slug}/{repo_slug}/contributors |
| Релизы | GET /repos/{org_slug}/{repo_slug}/releases |
| Популярность | Repository.rating.reaction_counts; positive_low = Like |
| AppSec | Не представлен в проверенной Swagger; пока unavailable |
| Полный каталог платформы | Не представлен в проверенной Swagger; configured-org discovery |

Base URL `https://api.sourcecraft.tech`, PAT в `Authorization: Bearer`. `page_size=100`, продолжение `page_token` / `next_page_token`. На 401/403/404 нет подмены ответа пустым списком. Отдельных `/commits`, `/appsec` или `/me/repos` адаптер не выдумывает.

Публичный Git: `https://git@git.sourcecraft.dev/{org}/{repo}.git`; username `git`. Для private/internal требуется PAT или SSH. Реализация использует PAT/askpass после проверки прав REST; SSH не используется.

CLI-обёртка вызывает только документированные `src repo list ORG --json` и `src issue list --repo ORG/REPO --json`. Формат CLI по умолчанию табличный, поэтому --json обязателен. CLI версии и profile provisioning — внешняя зависимость, wrapper не включён в автоматический discovery worker. Не используется `src do` или AI агент.

Я ID использует authorization code + PKCE, https://oauth.yandex.ru/authorize, POST https://oauth.yandex.ru/token и GET https://login.yandex.ru/info. Я ID profile ID и SourceCraft user ID не отождествляются; PAT подключается явно.

Результаты живых анонимных проверок: официальный REST `/repos/sourcecraft/documentation` возвратил 401 Unauthorized. Публичный Git документации доступен, SHA сохранён в `reports/live/*.json`. Таким образом Git-only отчёты реальны, но не заменяют API/AppSec-проверку.
