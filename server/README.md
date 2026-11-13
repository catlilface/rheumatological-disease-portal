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

Backend использует Python 3.11+, FastAPI, Uvicorn и `pydantic-settings`.

```text
server/
├── app/
│   ├── __init__.py
│   ├── main.py          # Приложение и GET /health
│   ├── settings.py      # Настройки из окружения и корневого .env
│   ├── database/        # Заглушка для будущего подключения к БД
│   └── domain/          # Заглушка для моделей и правил предметной области
├── tests/               # Проверки HTTP и настроек
├── pyproject.toml       # Зависимости приложения и тестов
├── Dockerfile
└── README.md
```

База данных пока не создаётся и не подключается. Пакеты `database` и `domain` содержат только `__init__.py`.

## 6. Настройки и установка

Команды этого раздела выполняются **из корня репозитория**. Нужны Python 3.11+ и pip. Команда `python` должна указывать на установленный Python; проверить версию можно через `python --version`.

### Windows (PowerShell)

```powershell
# Создать отдельное окружение backend
python -m venv server/.venv

# Установить приложение и зависимости для тестов
.\server\.venv\Scripts\python.exe -m pip install -e "./server[dev]"

# Создать .env, сохранив существующий файл, если он уже есть
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

### Linux / macOS (Bash)

```bash
python3 -m venv server/.venv
./server/.venv/bin/python -m pip install -e './server[dev]'

# Скопировать пример, только если .env ещё не существует
if [ ! -f .env ]; then cp .env.example .env; fi
```

Активация окружения не требуется: команды явно используют Python из `server/.venv`. Установка с `-e` позволяет запускать приложение из корня репозитория и сразу использовать изменения исходного кода.

Файл `.env` располагается рядом с `.env.example` в корне репозитория:

```dotenv
APP_NAME=Rheumatological Disease Portal
DEBUG=false
```

| Переменная | Назначение | Значение по умолчанию |
| --- | --- | --- |
| `APP_NAME` | Название приложения FastAPI | `Rheumatological Disease Portal` |
| `DEBUG` | Режим отладки FastAPI | `false` |

Приоритет настроек: **переменные окружения → корневой `.env` → значения по умолчанию**. Запуск без `.env` допустим. Неизвестные ключи общего `.env` игнорируются, путь к файлу не зависит от рабочей директории.

Для `DEBUG` используйте `true` или `false`. Например, унаследованное `DEBUG=release` вызовет ошибку валидации и остановит запуск. Переменная окружения перекрывает `.env`; в PowerShell её можно исправить для текущего терминала:

```powershell
$env:DEBUG = "false"
```

В Bash аналогичная команда: `export DEBUG=false`. Локальный `.env`, виртуальное окружение и кеши исключены из Git.

## 7. Локальный запуск

Выберите один вариант запуска; оба используют окружение из предыдущего раздела.

### Из корня репозитория

PowerShell:

```powershell
.\server\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Bash:

```bash
./server/.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

### Из директории server

PowerShell:

```powershell
cd server
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Bash:

```bash
cd server
./.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
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

PowerShell:

```powershell
.\server\.venv\Scripts\python.exe -m pytest -c server/pyproject.toml server/tests
```

Bash:

```bash
./server/.venv/bin/python -m pytest -c server/pyproject.toml server/tests
```

Если терминал уже находится в `server`, используйте `.\.venv\Scripts\python.exe -m pytest` в PowerShell или `./.venv/bin/python -m pytest` в Bash.

Тесты проверяют HTTP-контракт, загрузку `.env`, приоритет окружения, значения по умолчанию, валидацию `DEBUG` и независимость настроек от рабочей директории. Локальный `.env` разработчика не перезаписывается.

## 9. Docker

Нужен запущенный Docker с поддержкой Linux-контейнеров. Сборка выполняется **из корня репозитория**, даже если Dockerfile находится в `server`:

```bash
docker build -f server/Dockerfile -t rheumatology-backend .
docker run --rm -p 8000:8000 --env-file .env rheumatology-backend
```

Корневой `.env` создаётся в разделе 6. Для запуска с настройками примера можно заменить `.env` на `.env.example`; для значений по умолчанию можно убрать `--env-file .env` целиком.

Образ использует Python 3.12 slim, устанавливает зависимости без группы `dev` и запускает Uvicorn от пользователя `app` (UID 10001) на `0.0.0.0:8000`. `.env` не копируется в образ: Docker передаёт значения из `--env-file` как переменные окружения контейнера. `.dockerignore` исключает также локальное окружение, кеши и файлы других частей проекта.

Проверка контейнера — тот же адрес `http://localhost:8000/health`. Если порт 8000 занят локальным сервером или другим контейнером, остановите его либо замените проброс на `-p 8001:8000` и откройте `http://localhost:8001/health`.

Остановка — `Ctrl+C`; благодаря `--rm` остановленный контейнер удаляется. После изменения кода пересоберите образ и запустите новый контейнер. Файл `docker-compose.yaml` пока остаётся заглушкой; используйте команды `docker build` и `docker run` выше.
