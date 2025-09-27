import json
import logging
import pathlib

import torch
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from transformers import MarianMTModel, MarianTokenizer

from app.core.config import settings

# TODO: добавить timeddrotatingfilehandler
# чтобы логи не росли бесконечно
pathlib.Path("logs").mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("logs/log.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)

app = FastAPI()


model_path = "Helsinki-train-combined-dedup-cleaned-05072025"
tokenizer = MarianTokenizer.from_pretrained(model_path, local_files_only=True)
model = MarianMTModel.from_pretrained(model_path, trust_remote_code=True)


class TranslationRequest(BaseModel):
    source: str
    source_language: str
    target_language: str


@app.post("/translate")
async def translate_text(req: Request) -> dict:
    data = await req.json()
    logger.info(
        "🔵 Пришёл запрос от плагина:\n%s",
        json.dumps(data, ensure_ascii=False, indent=2),
    )

    # Определяем текст
    if "messages" in data:
        user_messages = [
            m["content"] for m in data.get("messages", []) if m["role"] == "user"
        ]
        text = user_messages[-1] if user_messages else ""
    elif "source" in data:
        text = data["source"]
    else:
        return {"translation": ""}

    # Перевод
    inputs = tokenizer([text], return_tensors="pt", padding=True)
    with torch.no_grad():
        output = model.generate(**inputs)
    translation = tokenizer.decode(output[0], skip_special_tokens=True)

    logger.info("✅ Перевод: %s → %s", text, translation)

    # Минимальный OpenAI-совместимый ответ
    response = {
        "id": "test",
        "object": "chat.completion",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": translation},
                "finish_reason": "stop",
            }
        ],
    }

    logger.info(
        "🟢 Ответ (OpenAI минимальный):\n%s",
        json.dumps(response, ensure_ascii=False, indent=2),
    )
    return response


@app.get("/test")
def test_translation() -> dict:
    test_text = "Hello, world!"
    inputs = tokenizer([test_text], return_tensors="pt", padding=True)
    with torch.no_grad():
        output = model.generate(**inputs)
    translation = tokenizer.decode(output[0], skip_special_tokens=True)
    logger.info("Тестовый перевод: %s → %s", test_text, translation)
    return {"source": test_text, "translation": translation}


@app.get("/ui", response_class=HTMLResponse)
def ui() -> str:
    return """
    <form action="/interactive" method="get">
      <input type="text" name="text" placeholder="Введите текст">
      <button type="submit">Перевести</button>
    </form>
    """


@app.get("/interactive")
def interactive_translation(text: str) -> dict:
    inputs = tokenizer([text], return_tensors="pt", padding=True)
    with torch.no_grad():
        output = model.generate(**inputs)
    translation = tokenizer.decode(output[0], skip_special_tokens=True)
    logger.info("Интерактивный перевод: %s → %s", text, translation)
    return {"source": text, "translation": translation}


if __name__ == "__main__":
    uvicorn.run(
        "app.__main__:app",
        host=settings.UVICORN_HOST,
        port=settings.UVICORN_PORT,
        log_config=None,
        reload=settings.UVICORN_RELOAD,
        workers=settings.UVICORN_WORKERS,
    )
