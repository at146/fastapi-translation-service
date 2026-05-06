import json
import secrets
from typing import Annotated

import torch
import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from transformers import MarianMTModel, MarianTokenizer

from app.core.config import Environment, settings
from app.tag_handler import replace_tags, restore_tags
from app.utils.logging import setup_logger

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

# TODO: должен прилетать json
@app.post("/translate", dependencies=[Depends(verify_bearer_token)])
async def translate_text(req: Request) -> dict:
    """
    С поддержкой XLIFF-тегов.
    """
    data = await req.json()
    logger.info(
        "Пришёл запрос от плагина:\n%s",
        json.dumps(data, ensure_ascii=False, indent=2),
    )

    # ── 1. Определяем текст ──────────────────────────────────────────────
    if "messages" in data:
        user_messages = [
            m["content"] for m in data.get("messages", []) if m["role"] == "user"
        ]
        text = user_messages[-1] if user_messages else ""
    elif "source" in data:
        text = data["source"]
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
    inputs = tokenizer([text_for_model], return_tensors="pt", padding=True)
    with torch.no_grad():
        output = model.generate(**inputs)
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
