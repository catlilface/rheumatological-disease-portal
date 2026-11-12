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
