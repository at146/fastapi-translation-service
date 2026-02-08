# FastAPI Translation Service

HTTP-сервис машинного перевода на базе модели [MarianMT](https://huggingface.co/docs/transformers/model_doc/marian) (Helsinki-NLP). Реализован на FastAPI и возвращает ответы в формате, совместимом с OpenAI Chat Completions API.

## Возможности

- **Перевод текста** через нейросетевую модель MarianMT (PyTorch, Transformers).
- **Авторизация** по Bearer-токену (`Authorization: Bearer <API_KEY>`).
- **Два формата запроса**:
  - объект с полем `source` (исходный текст);
  - объект с массивом `messages` в стиле OpenAI (берётся последнее сообщение с `role: "user"`).
- **Ответ в формате OpenAI**: структура `chat.completion` с полем `choices[].message.content` — переведённый текст.
- **Логирование** в консоль и в файлы (`logs/log.log`, `logs/error_log.log`).
- **Конфигурация** через переменные окружения (`.env`).
- **Docker**: сборка с [uv](https://docs.astral.sh/uv/), готовый образ для продакшена.

## Требования

- Python 3.10
- Локально скачанная модель MarianMT (например, Helsinki combined), путь задаётся в `MODEL_PATH`.

## Установка и запуск

### Локально

1. Клонировать репозиторий и перейти в каталог проекта.

2. Установить зависимости (рекомендуется через [uv](https://docs.astral.sh/uv/)):

   ```bash
   uv sync
   ```

   Либо через pip:

   ```bash
   pip install -r requirements.txt
   ```

3. Скопировать пример конфигурации и заполнить переменные:

   ```bash
   cp .env.example .env
   ```

   В `.env` задать:

   - `ENVIRONMENT` — `local` или `production` (в production отключаются Swagger и ReDoc).
   - `UVICORN_HOST`, `UVICORN_PORT`, `UVICORN_RELOAD`, `UVICORN_WORKERS` — параметры сервера.
   - `MODEL_PATH` — путь к каталогу с моделью MarianMT (например, `Helsinki-train-combined-dedup-cleaned-05072025`).
   - `API_KEY` — секретный ключ для заголовка `Authorization: Bearer <API_KEY>`.

4. Запустить приложение:

   ```bash
   python -m app
   ```

   По умолчанию документация доступна по адресам `/docs` (Swagger) и `/redoc` (ReDoc) в режиме `local`.

### Docker

1. Положить модель в каталог, указанный в `Dockerfile` (например, `Helsinki-train-combined-dedup-cleaned-05072025/`).

2. Задать переменные для образа в `.env`:

   - `DOCKER_IMAGE_BACKEND` — имя образа.
   - `TAG` — тег (по умолчанию `latest`).

3. Собрать и запустить через docker-compose:

   ```bash
   docker compose -f docker-compose-prod.yml up -d
   ```

   В `docker-compose-prod.yml` сервис настроен на `network_mode: host`, порт и воркеры задаются переменными окружения в `environment`.

## API

### `POST /translate`

Переводит текст. Требуется заголовок:

```http
Authorization: Bearer <API_KEY>
```

**Тело запроса (вариант 1):**

```json
{
  "source": "Hello, world!"
}
```

**Тело запроса (вариант 2, стиль OpenAI):**

```json
{
  "messages": [
    { "role": "user", "content": "Hello, world!" }
  ]
}
```

**Ответ (упрощённо):**

```json
{
  "id": "test",
  "object": "chat.completion",
  "choices": [
    {
      "index": 0,
      "message": { "role": "assistant", "content": "<переведённый текст>" },
      "finish_reason": "stop"
    }
  ]
}
```

При неверном или отсутствующем токене возвращается `401 Unauthorized`.

## Структура проекта

```
fastapi-translation-service/
├── app/
│   ├── __main__.py      # FastAPI-приложение, эндпоинт /translate, загрузка модели
│   ├── core/
│   │   └── config.py    # Настройки (Environment, Settings) из .env
│   └── utils/
│       └── logging.py   # Настройка логгера (консоль + файлы)
├── .env.example         # Пример переменных окружения
├── docker-compose-prod.yml
├── Dockerfile           # Сборка с uv, Python 3.10
├── pyproject.toml       # Зависимости и настройки Ruff
├── requirements.txt     # Экспорт зависимостей (uv)
└── uv.lock
```

## Зависимости (основные)

- **fastapi** — веб-фреймворк.
- **uvicorn** — ASGI-сервер.
- **transformers**, **torch** — MarianMT и инференс.
- **pydantic**, **pydantic-settings** — валидация и конфигурация из `.env`.

Управление зависимостями: [uv](https://docs.astral.sh/uv/) (в проекте есть `pyproject.toml` и `uv.lock`).
