# Frontend Service

Проект организован по принципу **монорепы**. Все сервисы хранятся в одном Git-репозитории, но для разработки рекомендуется загружать только необходимые компоненты.

## 1. Клонирование репозитория

Для оптимизации загрузки используется **Git Partial Clone + Sparse Checkout**.

```bash
git clone \
    --filter=blob:none \
    --sparse \
    https://github.com/catlilface/rheumatological-disease-portal.git
cd rheumatological-disease-portal
git sparse-checkout set frontend
```

После выполнения команд в рабочей директории будут доступны файлы сервиса `frontend` и файлы из корня репозитория.

`--filter=blob:none` позволяет не загружать содержимое всех файлов заранее, а `git sparse-checkout set frontend` ограничивает набор файлов в рабочей директории.

## 2. Правила работы с Git

### Ветки

Разработка ведётся в отдельных ветках. Название ветки должно соответствовать идентификатору задачи в трекере. Например: `MIS-123`.

### Коммиты

Сообщения коммитов должны:

- Быть написаны на английском языке.
- Кратко и однозначно описывать внесённые изменения.
- Соответствовать формату Conventional Commits (`feat:`, `chores:`, и тд).

## 3. Процесс разработки

Перед началом новой задачи необходимо обновить локальную ветку `main` и создать рабочую ветку.

```bash
# Переключиться на основную ветку
git switch main

# Получить последние изменения
git pull --ff-only origin main

# Создать ветку для задачи
git switch -c MIS-123
```

После внесения изменений:

```bash
# Проверить изменённые файлы
git status

# Добавить необходимые файлы
git add frontend/path/to/file

# Создать коммит
git commit -m "feat: implement awesome feature"

# Отправить ветку в GitHub
git push -u origin MIS-123
```

## 4. Pull Request и Code Review

После завершения разработки необходимо создать Pull Request в ветку `main` на GitHub.

Порядок действий:

1. Создать Pull Request с описанием изменений.
2. Убедиться, что все обязательные проверки CI успешно пройдены.
3. Добавить тимлида в ревью.
4. При необходимости внести исправления по результатам ревью.

**Тимлид приступает к Code Review только после успешного завершения обязательных проверок CI.**

## 5. Локальный запуск и проверки

Требуется Node.js 22 (версия указана в `.nvmrc`).

```bash
cd frontend
npm install       # заодно подключает git-хуки husky
npm run dev       # dev-сервер Vite
```

Откройте `http://localhost:5173`. Vite направляет запросы из `/api/` на
`https://mis.clfs.wtf`. Браузер обращается к BFF через origin фронтенда,
поскольку стенд ограничивает cross-origin запросы и использует сессионные cookie.
Для локального Go BFF задайте `BFF_PROXY_TARGET=http://localhost:8000` перед
запуском Vite.

Маршруты MVP

- `/screening` и `/screening/:screeningId` для новой и открытой анкеты.
- `/results/:resultId/versions/:version` для конкретной версии результата.
- `/library` и `/library/:slug` для библиотеки и статьи.
- `/doctor` для материала о подготовке к приёму.

HTTP-контракт доступен в [Scalar](https://mis.clfs.wtf/scalar) и в
[OpenAPI BFF](../contracts/http/bff-v1.openapi.yaml).
Пояснение к результату использует HTTP-команду с проверкой статуса операции.
Для подключения WSS нужны согласованные маршрут BFF, формат сообщений и правила доступа.

| Команда                | Что делает                     |
| ---------------------- | ------------------------------ |
| `npm run lint`         | линтер oxlint                  |
| `npm run format`       | форматирование Prettier        |
| `npm run format:check` | проверка форматирования        |
| `npm run typecheck`    | проверка типов TypeScript      |
| `npm test`             | тесты Vitest + Testing Library |
| `npm run build`        | production-сборка в `dist/`    |

Перед каждым коммитом husky запускает lint-staged (oxlint и Prettier для изменённых файлов), проверку типов и тесты. Те же проверки и сборка Docker-образа выполняются в GitHub Actions (`.github/workflows/frontend.yml`).

### Docker

```bash
cd frontend
docker build -t rheumatology-portal-frontend .
docker run --rm -p 8080:80 rheumatology-portal-frontend
```

Приложение будет доступно на http://localhost:8080.

Настройки nginx задаются переменными окружения (значения по умолчанию указаны в `Dockerfile`, пример лежит в корневом `.env.example`):

| Переменная                   | По умолчанию           | Назначение                                                                                             |
| ---------------------------- | ---------------------- | ------------------------------------------------------------------------------------------------------ |
| `NGINX_CLIENT_MAX_BODY_SIZE` | `100m`                 | максимальный размер загружаемого файла                                                                 |
| `NGINX_BACKEND_URL`          | `https://mis.clfs.wtf` | origin BFF для `/api/`, включая схему и при необходимости порт                                         |
| `NGINX_PUBLIC_ORIGIN`        | origin запроса         | публичный origin фронтенда при завершении TLS на внешнем прокси, например `https://portal.example.org` |
| `NGINX_RESOLVER`             | DNS контейнера         | переопределение DNS для поиска BFF                                                                     |

```bash
docker run --rm -p 8080:80 --env-file ../.env rheumatology-portal-frontend
```

Конфиг собирается при старте контейнера из `nginx.conf.template` (envsubst из официального образа nginx).

### Интеграционные тесты nginx

После запуска контейнера в другом терминале выполните `npm run test:integration`.
Тесты обращаются к работающему nginx по адресу http://localhost:8080 и проверяют
выдачу PDF, ответы для неизвестных документов и редиректы страниц со слешем.
Если контейнер доступен на другом адресе, задайте переменную `FRONTEND_URL`.
