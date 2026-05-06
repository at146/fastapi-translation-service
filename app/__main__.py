import json
import secrets
from typing import Annotated

import torch
import uvicorn
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from transformers import MarianMTModel, MarianTokenizer

from app.core.config import Environment, settings
from app.tag_handler import replace_tags, restore_tags
from app.utils.logging import setup_logger


class Message(BaseModel):
    role: str
    content: str


class TranslateRequest(BaseModel):
    messages: list[Message] | None = None
    source: str | None = None
    model: str | None = None
    max_tokens: int | None = None
    temperature: float | None = None

logger = setup_logger()


security = HTTPBearer()


async def verify_bearer_token(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)],
) -> None:
    """
    Проверяет header Authorization: Bearer <token>
    Возвращает словарь (можно вернуть объект user или claims),
    либо выбрасывает HTTPException.
    """
    # Проверяем, что схема — Bearer
    if credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication scheme",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Сравниваем токены безопасно (против timing-атак)
    if not secrets.compare_digest(credentials.credentials, settings.API_KEY):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )


if settings.ENVIRONMENT == Environment.PRODUCTION:
    app = FastAPI(docs_url=None, redoc_url=None)
else:
    app = FastAPI()


tokenizer = MarianTokenizer.from_pretrained(settings.MODEL_PATH, local_files_only=True)
model = MarianMTModel.from_pretrained(settings.MODEL_PATH, trust_remote_code=True)


@app.post("/translate", dependencies=[Depends(verify_bearer_token)])
async def translate_text(req: TranslateRequest) -> dict:
    """
    С поддержкой XLIFF-тегов.
    """
    logger.info(
        "Пришёл запрос от плагина:\n%s",
        req.model_dump_json(indent=2),
    )

    # ── 1. Определяем текст ──────────────────────────────────────────────
    if req.messages is not None:
        user_messages = [m.content for m in req.messages if m.role == "user"]
        text = user_messages[-1] if user_messages else ""
    elif req.source is not None:
        text = req.source
    else:
        return _openai_response("")

    if not text.strip():
        return _openai_response("")

    # ── 2. Замена тегов на плейсхолдеры ──────────────────────────────────
    tag_result = replace_tags(text)

    if tag_result.has_tags:
        logger.info(
            "Найдено %d тегов, заменены на плейсхолдеры",
            len(tag_result.mappings),
        )
        logger.debug(
            "Маппинг тегов:\n%s",
            "\n".join(
                f"  {m.placeholder} ← {m.original_tag}" for m in tag_result.mappings
            ),
        )

    text_for_model = tag_result.cleaned_text

    # ── 3. Перевод моделью ───────────────────────────────────────────────
    # truncation=True + max_length=512: MarianMT обучена на окне в 512 токенов,
    # без обрезки длинный ввод вызывает RuntimeError: bad allocation в beam search
    inputs = tokenizer(
        [text_for_model],
        return_tensors="pt",
        padding=True,
        truncation=True,
        max_length=512,
    )
    with torch.no_grad():
        # max_length=512: ограничивает сторону декодера — без этого beam search
        # пытается выделить память под очень длинные последовательности
        output = model.generate(**inputs, max_length=512)
    translation = tokenizer.decode(output[0], skip_special_tokens=True)

    logger.info("Сырой перевод: %s → %s", text_for_model, translation)

    # ── 4. Восстановление тегов ──────────────────────────────────────────
    if tag_result.has_tags:
        restore_result = restore_tags(translation, tag_result.mappings, text)
        translation = restore_result.restored_text

        if not restore_result.success:
            logger.warning(
                "Восстановление тегов с ошибками: %s | fallback=%s",
                "; ".join(restore_result.warnings),
                restore_result.used_fallback,
            )
        else:
            if restore_result.warnings:
                logger.warning(
                    "Восстановление тегов с предупреждениями: %s",
                    "; ".join(restore_result.warnings),
                )
            logger.info("Теги восстановлены: %s", translation)

    # ── 5. Ответ в OpenAI-совместимом формате ────────────────────────────
    response = _openai_response(translation)
    logger.info(
        "Ответ:\n%s",
        json.dumps(response, ensure_ascii=False, indent=2),
    )
    return response

# TODO: посмотреть как получает ответ плагин memoQ
def _openai_response(content: str) -> dict:
    """Формирует минимальный OpenAI-совместимый ответ."""
    return {
        "id": "test",
        "object": "chat.completion",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
    }


# @app.get("/test")
# def test_translation() -> dict:
#     test_text = "Hello, world!"
#     inputs = tokenizer([test_text], return_tensors="pt", padding=True)
#     with torch.no_grad():
#         output = model.generate(**inputs)
#     translation = tokenizer.decode(output[0], skip_special_tokens=True)
#     logger.info("Тестовый перевод: %s → %s", test_text, translation)
#     return {"source": test_text, "translation": translation}


# @app.get("/ui", response_class=HTMLResponse)
# def ui() -> str:
#     return """
#     <form action="/interactive" method="get">
#       <input type="text" name="text" placeholder="Введите текст">
#       <button type="submit">Перевести</button>
#     </form>
#     """


# @app.get("/interactive")
# def interactive_translation(text: str) -> dict:
#     inputs = tokenizer([text], return_tensors="pt", padding=True)
#     with torch.no_grad():
#         output = model.generate(**inputs)
#     translation = tokenizer.decode(output[0], skip_special_tokens=True)
#     logger.info("Интерактивный перевод: %s → %s", text, translation)
#     return {"source": text, "translation": translation}


if __name__ == "__main__":
    uvicorn.run(
        "app.__main__:app",
        host=settings.UVICORN_HOST,
        port=settings.UVICORN_PORT,
        log_config=None,
        reload=settings.UVICORN_RELOAD,
        workers=settings.UVICORN_WORKERS,
    )
