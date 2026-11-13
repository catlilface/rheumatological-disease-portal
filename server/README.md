# Server Service

Проект организован по принципу **монорепы**. Все сервисы хранятся в одном Git-репозитории, но для разработки рекомендуется загружать только необходимые компоненты.

## 1. Клонирование репозитория

Для оптимизации загрузки используется **Git Partial Clone + Sparse Checkout**.

```bash
git clone \
    --filter=blob:none \
    --sparse \
    https://github.com/catlilface/rheumatological-disease-portal.git
cd rheumatological-disease-portal
git sparse-checkout set server
```

После выполнения команд в рабочей директории будут доступны файлы сервиса `server` и файлы из корня репозитория.

`--filter=blob:none` позволяет не загружать содержимое всех файлов заранее, а `git sparse-checkout set server` ограничивает набор файлов в рабочей директории.

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
git add server/path/to/file

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

## 5. Структура backend

Backend использует Python 3.15, FastAPI, Uvicorn и `pydantic-settings`. Окружением и зависимостями управляет `uv`.

```text
server/
├── app/
│   ├── main.py          # Приложение и GET /health
│   ├── settings.py      # Настройки из окружения и корневого .env
│   ├── database/        # Заглушка для будущего подключения к БД
│   └── domain/          # Заглушка для моделей и правил предметной области
├── tests/               # Проверки HTTP и настроек
├── pyproject.toml       # Зависимости приложения и тестов
├── uv.lock              # Зафиксированные версии зависимостей
├── .python-version      # Python 3.15 для uv
├── Dockerfile
└── README.md
```

База данных пока не создаётся и не подключается. Пакеты `database` и `domain` содержат только `__init__.py`.

## 6. Настройки и установка

Команды этого раздела выполняются **из корня репозитория**. Установите `uv` по [официальной инструкции](https://docs.astral.sh/uv/getting-started/installation/) и проверьте его доступность командой `uv --version`.

```bash
uv python install 3.15
uv sync --project server --locked
uv run --project server --locked python --version
```

`uv` создаёт `server/.venv`, устанавливает приложение и группу зависимостей `dev` из `uv.lock`. Версия Python задана в `server/.python-version` и ограничена веткой 3.15 в `pyproject.toml`. Активация окружения и ручной запуск pip не требуются.

Создайте корневой `.env`, если он ещё не существует:

### Windows (PowerShell)

```powershell
# Создать .env, сохранив существующий файл, если он уже есть
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

### Linux / macOS (Bash)

```bash
# Скопировать пример, только если .env ещё не существует
if [ ! -f .env ]; then cp .env.example .env; fi
```

`server/uv.lock` хранится в Git. После изменения зависимостей обновляйте его через `uv`, а не вручную. Например, `uv add --project server package-name` добавляет рабочую зависимость, а `uv add --project server --dev package-name` — зависимость для разработки. Команда `uv lock --project server` обновляет lock-файл после ручного изменения `pyproject.toml`; `--locked` при установке обнаруживает несоответствие файлов.

Файл `.env` располагается рядом с `.env.example` в корне репозитория:

```dotenv
APP_NAME=Rheumatological Disease Portal
DEBUG=false
ALLOWED_HOSTS=["localhost","127.0.0.1"]
CORS_ALLOW_ORIGINS=["http://localhost:3000","http://localhost:5173"]
CORS_ALLOW_METHODS=["GET"]
CORS_ALLOW_HEADERS=["Content-Type","Authorization"]
CORS_ALLOW_CREDENTIALS=false
CORS_EXPOSE_HEADERS=[]
CORS_MAX_AGE=600
```

| Переменная | Назначение | Значение по умолчанию |
| --- | --- | --- |
| `APP_NAME` | Название приложения FastAPI | `Rheumatological Disease Portal` |
| `DEBUG` | Режим отладки FastAPI | `false` |
| `ALLOWED_HOSTS` | Допустимые значения Host для backend | `["localhost","127.0.0.1"]` |
| `CORS_ALLOW_ORIGINS` | Origins frontend, которым разрешено читать ответы API | `[]` |
| `CORS_ALLOW_METHODS` | Разрешённые методы CORS | `["GET"]` |
| `CORS_ALLOW_HEADERS` | Дополнительные заголовки CORS | `[]` |
| `CORS_ALLOW_CREDENTIALS` | Разрешить credentialed-запросы браузера, например с cookies | `false` |
| `CORS_EXPOSE_HEADERS` | Дополнительные заголовки ответа, доступные JavaScript | `[]` |
| `CORS_MAX_AGE` | Время кеширования preflight-ответа в секундах | `600` |

Приоритет настроек: **переменные окружения → корневой `.env` → значения по умолчанию**. Запуск без `.env` допустим. Неизвестные ключи общего `.env` игнорируются, путь к файлу не зависит от рабочей директории.

Для `DEBUG` используйте `true` или `false`. Например, унаследованное `DEBUG=release` вызовет ошибку валидации и остановит запуск. Переменная окружения перекрывает `.env`; в PowerShell её можно исправить для текущего терминала:

```powershell
$env:DEBUG = "false"
```

В Bash аналогичная команда: `export DEBUG=false`. Локальный `.env`, виртуальное окружение и кеши исключены из Git.

### CORS и разрешённые хосты

Это две разные проверки:

- `ALLOWED_HOSTS` проверяет **Host backend**, например `localhost` или `api.example.com`. Указывайте имена без `http://`, порта и пути. Проверка выполняется до CORS, включая preflight; запрос с неизвестным Host получает HTTP `400`.
- `CORS_ALLOW_ORIGINS` перечисляет **адреса frontend** со схемой и портом, например `http://localhost:5173`, без пути и завершающего `/`. `http://localhost:5173` и `http://127.0.0.1:5173` — разные origins.

Все списки записываются JSON-массивами: `["value1","value2"]`, а не строкой через запятую. Формат подходит и для чтения `.env` приложением, и для `docker run --env-file .env`: не оборачивайте весь JSON в дополнительные кавычки. Существующий `.env` не обновляется автоматически — перенесите нужные переменные из `.env.example` вручную.

Без настройки CORS список origins пуст. В `.env.example` приведены локальные адреса frontend на портах 3000 и 5173; замените их на адрес своего frontend. Для доступа к backend по домену или IP стенда добавьте этот домен или IP в `ALLOWED_HOSTS`.

Для `CORS_ALLOW_CREDENTIALS=true` задайте явные списки origins, методов и заголовков: `"*"` в этих трёх списках вызывает ошибку настройки при запуске. `CORS_MAX_AGE` не может быть отрицательным. Пустой `ALLOWED_HOSTS` также считается ошибкой настройки.

CORS регулирует доступ браузера к ответам и не заменяет авторизацию. Обычный GET с запрещённым Origin может вернуть HTTP `200`, но без `Access-Control-Allow-Origin`, поэтому браузер не даст JavaScript прочитать ответ. Preflight с запрещённым origin, методом или заголовком получает HTTP `400`. Разрешение метода в CORS не создаёт соответствующий маршрут API: сейчас приложение реализует только `GET /health`.

После изменения настроек перезапустите backend; для Docker пересоздайте контейнер с обновлённым `--env-file`.

## 7. Локальный запуск

Выберите один вариант запуска; оба используют окружение из предыдущего раздела.

### Из корня репозитория

Команда одинакова для PowerShell и Bash:

```bash
uv run --project server --locked uvicorn app.main:app --host 127.0.0.1 --port 8000
```

### Из директории server

```bash
cd server
uv run --locked uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Для автоматического перезапуска при изменении кода добавьте `--reload`. Остановка сервера — `Ctrl+C`.

## 8. Проверка health и тесты

Единственный эндпоинт — **`GET http://localhost:8000/health`**. Он проверяет доступность приложения, без обращения к БД. Ожидаемый ответ: HTTP `200` и JSON:

```json
{"status": "ok"}
```

Проверка в PowerShell:

```powershell
Invoke-RestMethod http://localhost:8000/health
```

Проверка в Bash:

```bash
curl -i http://localhost:8000/health
```

На `/`, `/docs`, `/redoc` и `/openapi.json` возвращается **404**: корневой маршрут не добавлен, а служебные маршруты документации отключены. Открывайте именно `/health`.

Запуск всех тестов **из корня репозитория**, без запущенного сервера:

```bash
uv run --project server --locked python -m pytest -c server/pyproject.toml server/tests
```

Если терминал уже находится в `server`, используйте `uv run --locked python -m pytest`. Команды одинаковы для PowerShell и Bash.

Тесты проверяют HTTP-контракт, загрузку `.env`, приоритет окружения, валидацию настроек и независимость от рабочей директории. Дополнительно проверяются разрешённые/запрещённые hosts и origins, CORS-заголовки, preflight и credentials. В тестах изолируются переменные окружения и локальный `.env` разработчика; сам файл не перезаписывается.

## 9. Docker

Нужен запущенный Docker с поддержкой Linux-контейнеров. Сборка выполняется **из корня репозитория**, даже если Dockerfile находится в `server`:

```bash
docker build -f server/Dockerfile -t rheumatology-backend .
docker run --rm -p 8000:8000 --env-file .env rheumatology-backend
```

Корневой `.env` создаётся в разделе 6. Для запуска с настройками примера можно заменить `.env` на `.env.example`; для значений по умолчанию можно убрать `--env-file .env` целиком.

Образ собирается на базе `ghcr.io/astral-sh/uv:python3.15-trixie-slim` с Python 3.15 и предустановленным `uv`. Зависимости устанавливаются через `uv sync --locked --no-dev`, приложение — без editable-установки. Изменение исходников не переустанавливает зависимости, пока `pyproject.toml` и `uv.lock` остаются прежними. Uvicorn запускается из созданного окружения от пользователя `app` (UID 10001) на `0.0.0.0:8000`, без повторной синхронизации при старте. `.env` не копируется в образ: Docker передаёт значения из `--env-file` как переменные окружения контейнера. `.dockerignore` исключает также локальное окружение, кеши и файлы других частей проекта.

Проверка контейнера — тот же адрес `http://localhost:8000/health`. Если порт 8000 занят локальным сервером или другим контейнером, остановите его либо замените проброс на `-p 8001:8000` и откройте `http://localhost:8001/health`.

Остановка — `Ctrl+C`; благодаря `--rm` остановленный контейнер удаляется. После изменения кода пересоберите образ и запустите новый контейнер. Файл `docker-compose.yaml` пока остаётся заглушкой; используйте команды `docker build` и `docker run` выше.
