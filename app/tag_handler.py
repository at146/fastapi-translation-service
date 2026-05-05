"""
tag_handler.py — Модуль обработки XML/XLIFF-тегов для NMT-перевода.

Заменяет XLIFF-теги на плейсхолдеры перед отправкой в модель,
восстанавливает теги после перевода.

Поддерживаемые теги:
  Парные:   <g …>…</g>, <ph …>…</ph>, <bpt …>…</bpt>/<ept …>…</ept>,
            <mrk …>…</mrk>, <hi …>…</hi>
  Самозакрывающиеся: <x …/>, <bx …/>, <ex …/>

Плейсхолдер: __TAG<N>__  (где N — порядковый номер, начиная с 1)
"""

from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Regex для поиска XLIFF-тегов
# ---------------------------------------------------------------------------

# Самозакрывающиеся теги: <x …/>, <bx …/>, <ex …/>
_SELF_CLOSING_RE = re.compile(
    r"<(?:x|bx|ex)\b[^>]*/\s*>",
    re.IGNORECASE,
)

# Открывающие теги парных элементов: <g …>, <ph …>, <bpt …>, <mrk …>, <hi …>
_OPEN_TAG_RE = re.compile(
    r"<(?:g|ph|bpt|ept|mrk|hi)\b[^>]*>",
    re.IGNORECASE,
)

# Закрывающие теги парных элементов: </g>, </ph>, </bpt>, </mrk>, </hi>
_CLOSE_TAG_RE = re.compile(
    r"</(?:g|ph|bpt|ept|mrk|hi)\s*>",
    re.IGNORECASE,
)

# Любой поддерживаемый XLIFF-тег (для единого прохода)
_ANY_TAG_RE = re.compile(
    r"</?(?:g|ph|bpt|ept|mrk|hi|x|bx|ex)\b[^>]*/?\s*>",
    re.IGNORECASE,
)

# Паттерн плейсхолдера в переведённом тексте
_PLACEHOLDER_RE = re.compile(r"__TAG(\d+)__")


# ---------------------------------------------------------------------------
# Структуры данных
# ---------------------------------------------------------------------------


@dataclass
class TagMapping:
    """Маппинг между плейсхолдером и оригинальным тегом."""

    placeholder: str  # например "__TAG1__"
    original_tag: str  # например '<g id="1">'
    index: int  # порядковый номер (1-based)


@dataclass
class TagProcessingResult:
    """Результат замены тегов на плейсхолдеры."""

    cleaned_text: str  # текст с плейсхолдерами вместо тегов
    mappings: list[TagMapping] = field(default_factory=list)
    has_tags: bool = False  # были ли теги в исходном тексте


@dataclass
class TagRestorationResult:
    """Результат восстановления тегов в переведённом тексте."""

    restored_text: str  # текст с восстановленными тегами
    success: bool = True  # успешно ли восстановление
    warnings: list[str] = field(default_factory=list)
    used_fallback: bool = False  # был ли использован fallback


# ---------------------------------------------------------------------------
# Основной класс
# ---------------------------------------------------------------------------


class XliffTagHandler:
    """
    Обработчик XLIFF-тегов для NMT-перевода.

    Пример использования:
        handler = XliffTagHandler()

        # Перед переводом
        result = handler.replace_tags(source_text)
        cleaned = result.cleaned_text   # отправить в модель

        # После перевода
        restored = handler.restore_tags(
            translated_text,
            result.mappings,
            source_text,
        )
        final = restored.restored_text
    """

    def __init__(
        self, placeholder_prefix: str = "__TAG", placeholder_suffix: str = "__"
    ):
        self._prefix = placeholder_prefix
        self._suffix = placeholder_suffix

    # ---- public API -------------------------------------------------------

    def replace_tags(self, text: str) -> TagProcessingResult:
        """
        Заменяет все XLIFF-теги в тексте на плейсхолдеры.

        Returns:
            TagProcessingResult с очищенным текстом и маппингом.
        """
        if not text:
            return TagProcessingResult(cleaned_text=text, has_tags=False)

        mappings: list[TagMapping] = []
        counter = 0

        def _replacer(match: re.Match) -> str:
            nonlocal counter
            counter += 1
            tag = match.group(0)
            ph = f"{self._prefix}{counter}{self._suffix}"
            mappings.append(TagMapping(placeholder=ph, original_tag=tag, index=counter))
            return ph

        cleaned = _ANY_TAG_RE.sub(_replacer, text)

        return TagProcessingResult(
            cleaned_text=cleaned,
            mappings=mappings,
            has_tags=len(mappings) > 0,
        )

    def restore_tags(
        self,
        translated_text: str,
        mappings: list[TagMapping],
        source_text: str,
    ) -> TagRestorationResult:
        """
        Восстанавливает XLIFF-теги в переведённом тексте.

        Стратегия:
          1. Прямая замена плейсхолдеров на оригинальные теги.
          2. Если модель переставила плейсхолдеры — переупорядочивание.
          3. Если модель потеряла плейсхолдеры — вставка потерянных тегов.
          4. Если всё совсем плохо — fallback на исходный текст.

        Args:
            translated_text: текст после NMT-модели (с плейсхолдерами).
            mappings:        маппинг из replace_tags().
            source_text:     оригинальный исходный текст (для fallback).

        Returns:
            TagRestorationResult с восстановленным текстом.
        """
        if not mappings:
            return TagRestorationResult(restored_text=translated_text)

        warnings: list[str] = []

        try:
            # --- Шаг 1: Нормализация форматов плейсхолдеров из модели ----------
            # Модель может выдать {TAG1}, [TAG1], <TAG1> вместо __TAG1__
            translated_text = self._normalize_placeholders(translated_text)

            # --- Шаг 2: Прямая замена имеющихся плейсхолдеров -----------------
            result = translated_text

            found_phs = set(_PLACEHOLDER_RE.findall(result))
            expected_phs = {str(m.index) for m in mappings}

            # Заменяем все найденные плейсхолдеры
            for m in mappings:
                if m.placeholder in result:
                    result = result.replace(m.placeholder, m.original_tag, 1)

            # --- Шаг 3: Проверка потерянных тегов ------------------------------
            missing_indices = expected_phs - found_phs
            if missing_indices:
                missing_mappings = [
                    m for m in mappings if str(m.index) in missing_indices
                ]
                warnings.append(
                    f"Модель потеряла {len(missing_mappings)} тег(ов): "
                    f"{[m.placeholder for m in missing_mappings]}"
                )
                result = self._insert_missing_tags(
                    result, missing_mappings, source_text
                )

            # --- Шаг 4: Валидация результата -----------------------------------
            if not self._validate_tag_structure(result, mappings):
                warnings.append("Нарушена структура тегов, попытка исправления")
                result = self._fix_tag_order(result, mappings, source_text)

            # Финальная проверка
            if not self._has_minimum_tags(result, mappings):
                warnings.append(
                    "Критическая ошибка: невозможно восстановить теги,"
                    " fallback на исходный текст"
                )
                logger.error(
                    "Tag restoration failed. Source: %r | Translated: %r",
                    source_text,
                    translated_text,
                )
                return TagRestorationResult(
                    restored_text=source_text,
                    success=False,
                    warnings=warnings,
                    used_fallback=True,
                )

            if warnings:
                logger.warning("Tag restoration warnings: %s", "; ".join(warnings))

            return TagRestorationResult(
                restored_text=result,
                success=True,
                warnings=warnings,
            )

        except Exception as e:
            logger.exception("Critical error during tag restoration: %s", e)
            return TagRestorationResult(
                restored_text=source_text,
                success=False,
                warnings=[f"Исключение при восстановлении тегов: {e}"],
                used_fallback=True,
            )

    # ---- private helpers --------------------------------------------------

    def _insert_missing_tags(
        self,
        text: str,
        missing: list[TagMapping],
        source_text: str,
    ) -> str:
        """
        Вставляет потерянные теги в переведённый текст.

        Стратегия: для каждого потерянного тега определяем его
        относительную позицию в исходном тексте (начало / конец / процент)
        и вставляем в аналогичную позицию перевода.
        """
        if not missing or not text:
            return text

        src_len = len(source_text) if source_text else 1

        # Собираем информацию о позициях тегов в исходном тексте
        insertions: list[tuple[float, str]] = []
        for m in missing:
            pos = source_text.find(m.original_tag) if source_text else -1
            if pos == -1:
                # Тег не найден в исходнике — ставим в конец
                relative_pos = 1.0
            else:
                relative_pos = pos / src_len
            insertions.append((relative_pos, m.original_tag))

        # Сортируем по позиции (от конца к началу, чтобы не сбивать индексы)
        insertions.sort(key=lambda x: x[0], reverse=True)

        result = text
        for rel_pos, tag in insertions:
            result_len = len(result)  # пересчитываем после каждой вставки
            insert_pos = int(rel_pos * result_len)
            # Корректируем, чтобы не разрывать слова
            insert_pos = self._find_word_boundary(result, insert_pos)
            result = result[:insert_pos] + tag + result[insert_pos:]

        return result

    @staticmethod
    def _find_word_boundary(text: str, pos: int) -> int:
        """Ищет ближайшую границу слова (пробел) к позиции pos."""
        if pos >= len(text):
            return len(text)
        if pos <= 0:
            return 0

        # Ищем ближайший пробел вправо
        right = pos
        while right < len(text) and not text[right].isspace():
            right += 1

        # Ищем ближайший пробел влево
        left = pos
        while left > 0 and not text[left - 1].isspace():
            left -= 1

        # Выбираем ближайшую границу
        if right - pos <= pos - left:
            return right
        return left

    def _fix_tag_order(
        self,
        text: str,
        mappings: list[TagMapping],
        source_text: str,
    ) -> str:
        """
        Пытается исправить порядок тегов в переведённом тексте.

        Извлекает все теги из результата, определяет правильный порядок
        из исходного текста и переставляет их.
        """
        # Извлекаем теги из текущего результата
        tags_in_result = _ANY_TAG_RE.findall(text)
        if not tags_in_result:
            return text

        # Порядок тегов из исходного текста
        tags_in_source = _ANY_TAG_RE.findall(source_text)

        # Удаляем все теги из результата
        text_without_tags = _ANY_TAG_RE.sub("", text)

        # Определяем порядок тегов из исходного текста с учётом количества вхождений
        remaining = Counter(tags_in_result)
        ordered_tags = []
        for t in tags_in_source:
            if remaining[t] > 0:
                ordered_tags.append(t)
                remaining[t] -= 1

        # Добавляем теги из результата, которых не было в исходнике
        for t, count in remaining.items():
            ordered_tags.extend([t] * count)

        # Находим позиции тегов в исходном тексте (относительные)
        src_no_tags = _ANY_TAG_RE.sub("", source_text)
        src_no_tags_len = len(src_no_tags) if src_no_tags else 1
        result_no_tags_len = len(text_without_tags) if text_without_tags else 1

        result = text_without_tags
        # Вставляем в порядке из исходного текста, от конца к началу
        tag_positions: list[tuple[int, str]] = []
        search_start: dict[str, int] = {}
        for tag in ordered_tags:
            start = search_start.get(tag, 0)
            pos_in_src = source_text.find(tag, start)
            if pos_in_src >= 0:
                search_start[tag] = pos_in_src + len(tag)
            # Считаем чисто-текстовую позицию (без тегов)
            text_before_tag = (
                _ANY_TAG_RE.sub("", source_text[:pos_in_src]) if pos_in_src >= 0 else ""
            )
            rel_pos = (
                len(text_before_tag) / src_no_tags_len if src_no_tags_len > 0 else 0
            )
            abs_pos = int(rel_pos * result_no_tags_len)
            tag_positions.append((abs_pos, tag))

        # Вставляем от конца к началу
        tag_positions.sort(key=lambda x: x[0], reverse=True)
        for abs_pos, tag in tag_positions:
            clamped_pos = min(abs_pos, len(result))
            result = result[:clamped_pos] + tag + result[clamped_pos:]

        return result

    @staticmethod
    def _validate_tag_structure(text: str, mappings: list[TagMapping]) -> bool:
        """
        Проверяет корректность XML-структуры тегов через реальный парсер.
        Возвращает True, если структура валидна.
        """
        if not mappings:
            return True
        try:
            ET.fromstring(f"<root>{text}</root>")
            return True
        except ET.ParseError:
            return False

    @staticmethod
    def _normalize_placeholders(text: str) -> str:
        """
        Нормализует альтернативные форматы плейсхолдеров, которые может выдать модель.
        {TAG1}, [TAG1], <TAG1> → __TAG1__
        """
        text = re.sub(r"\{TAG(\d+)\}", r"__TAG\1__", text, flags=re.I)
        text = re.sub(r"\[TAG(\d+)\]", r"__TAG\1__", text, flags=re.I)
        return re.sub(r"<TAG(\d+)>", r"__TAG\1__", text, flags=re.I)

    @staticmethod
    def _has_minimum_tags(text: str, mappings: list[TagMapping]) -> bool:
        """
        Проверяет, что в тексте есть хотя бы часть ожидаемых тегов.
        Если потеряно больше 50% тегов — считаем результат непригодным.
        """
        if not mappings:
            return True

        tags_found = _ANY_TAG_RE.findall(text)
        expected_count = len(mappings)
        found_count = len(tags_found)

        return found_count >= expected_count * 0.5


# ---------------------------------------------------------------------------
# Convenience functions
# ---------------------------------------------------------------------------

_default_handler = XliffTagHandler()


def replace_tags(text: str) -> TagProcessingResult:
    """Заменяет XLIFF-теги на плейсхолдеры (функция-обёртка)."""
    return _default_handler.replace_tags(text)


def restore_tags(
    translated_text: str,
    mappings: list[TagMapping],
    source_text: str,
) -> TagRestorationResult:
    """Восстанавливает XLIFF-теги из плейсхолдеров (функция-обёртка)."""
    return _default_handler.restore_tags(translated_text, mappings, source_text)
