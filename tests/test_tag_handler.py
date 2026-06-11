"""
test_tag_handler.py — Тесты для модуля tag_handler.
Запуск: uv run pytest tests/ или uv run python tests/test_tag_handler.py
"""

from app.tag_handler import XliffTagHandler, replace_tags, restore_tags


def test_basic_paired_tags() -> None:
    """Парные теги g, ph, mrk, hi."""
    handler = XliffTagHandler()

    text = 'Нажмите <g id="1">кнопку</g> для продолжения.'
    result = handler.replace_tags(text)

    assert result.has_tags
    assert len(result.mappings) == 2  # <g id="1"> и </g>
    assert "__TAG1__" in result.cleaned_text
    assert "__TAG2__" in result.cleaned_text
    assert "<g" not in result.cleaned_text
    assert "</g>" not in result.cleaned_text
    print(f"  ✓ replace: {result.cleaned_text!r}")  # noqa: T201

    # Имитация перевода: модель сохранила плейсхолдеры
    translated = "Click __TAG1__button__TAG2__ to continue."
    restored = handler.restore_tags(translated, result.mappings, text)

    assert restored.success
    assert '<g id="1">' in restored.restored_text
    assert "</g>" in restored.restored_text
    print(f"  ✓ restore: {restored.restored_text!r}")  # noqa: T201


def test_self_closing_tags() -> None:
    """Самозакрывающиеся теги x, bx, ex."""
    handler = XliffTagHandler()

    text = 'Строка 1<x id="1"/>Строка 2<bx id="2"/>Строка 3<ex id="3"/>'
    result = handler.replace_tags(text)

    assert result.has_tags
    assert len(result.mappings) == 3
    print(f"  ✓ replace: {result.cleaned_text!r}")  # noqa: T201

    translated = "Line 1__TAG1__Line 2__TAG2__Line 3__TAG3__"
    restored = handler.restore_tags(translated, result.mappings, text)

    assert restored.success
    assert '<x id="1"/>' in restored.restored_text
    print(f"  ✓ restore: {restored.restored_text!r}")  # noqa: T201


def test_bpt_ept_tags() -> None:
    """Парные теги bpt/ept (каждый имеет открывающий и закрывающий)."""
    handler = XliffTagHandler()

    text = '<bpt id="1">&lt;b&gt;</bpt>Bold text<ept id="1">&lt;/b&gt;</ept>'
    result = handler.replace_tags(text)

    assert result.has_tags
    # <bpt>, </bpt>, <ept>, </ept> = 4 маппинга
    assert len(result.mappings) == 4
    print(f"  ✓ replace: {result.cleaned_text!r}")  # noqa: T201

    translated = "__TAG1__&lt;b&gt;__TAG2__Жирный текст__TAG3__&lt;/b&gt;__TAG4__"
    restored = handler.restore_tags(translated, result.mappings, text)

    assert restored.success
    assert '<bpt id="1">' in restored.restored_text
    assert '<ept id="1">' in restored.restored_text
    print(f"  ✓ restore: {restored.restored_text!r}")  # noqa: T201


def test_mixed_tags() -> None:
    """Смешанные теги в одном сегменте."""
    handler = XliffTagHandler()

    text = (
        '<g id="1">Hello</g> <x id="2"/> '
        '<bpt id="3">&lt;a&gt;</bpt>link<ept id="3">&lt;/a&gt;</ept>'
    )
    result = handler.replace_tags(text)

    assert result.has_tags
    # <g>, </g>, <x/>, <bpt>, </bpt>, <ept>, </ept> = 7
    assert len(result.mappings) == 7
    print(f"  ✓ replace: {result.cleaned_text!r}")  # noqa: T201

    translated = (
        "__TAG1__Привет__TAG2__ __TAG3__ "
        "__TAG4__&lt;a&gt;__TAG5__ссылка__TAG6__&lt;/a&gt;__TAG7__"
    )
    restored = handler.restore_tags(translated, result.mappings, text)

    assert restored.success
    print(f"  ✓ restore: {restored.restored_text!r}")  # noqa: T201


def test_no_tags() -> None:
    """Текст без тегов."""
    handler = XliffTagHandler()

    text = "Простой текст без тегов."
    result = handler.replace_tags(text)

    assert not result.has_tags
    assert len(result.mappings) == 0
    assert result.cleaned_text == text
    print(f"  ✓ no tags: {result.cleaned_text!r}")  # noqa: T201


def test_empty_text() -> None:
    """Пустой текст."""
    handler = XliffTagHandler()

    result = handler.replace_tags("")
    assert not result.has_tags
    assert result.cleaned_text == ""
    print("  ✓ empty text")  # noqa: T201


def test_model_lost_tags() -> None:
    """Модель потеряла часть плейсхолдеров."""
    handler = XliffTagHandler()

    text = '<g id="1">Hello</g> world'
    result = handler.replace_tags(text)

    # Модель потеряла __TAG2__ (</g>)
    translated = "__TAG1__Привет мир"
    restored = handler.restore_tags(translated, result.mappings, text)

    assert restored.success  # Должен вставить потерянный тег
    assert "</g>" in restored.restored_text
    assert len(restored.warnings) > 0
    print(f"  ✓ lost tag restored: {restored.restored_text!r}")  # noqa: T201
    print(f"    warnings: {restored.warnings}")  # noqa: T201


def test_model_lost_all_tags() -> None:
    """Модель потеряла все плейсхолдеры — insert_missing_tags вставляет теги обратно."""
    handler = XliffTagHandler()

    text = '<g id="1">Hello</g>'
    result = handler.replace_tags(text)

    # Модель потеряла все плейсхолдеры
    translated = "Привет"
    restored = handler.restore_tags(translated, result.mappings, text)

    # insert_missing_tags вставит оба тега → _has_minimum_tags True → no fallback
    assert '<g id="1">' in restored.restored_text
    assert "</g>" in restored.restored_text
    assert len(restored.warnings) > 0
    assert restored.success is True
    assert restored.used_fallback is False


def test_convenience_functions() -> None:
    """Тест обёрток replace_tags / restore_tags."""
    text = '<hi type="bold">Important</hi>'
    result = replace_tags(text)

    assert result.has_tags
    assert "__TAG1__" in result.cleaned_text

    translated = "__TAG1__Важно__TAG2__"
    restored = restore_tags(translated, result.mappings, text)

    assert restored.success
    assert '<hi type="bold">' in restored.restored_text
    assert "</hi>" in restored.restored_text
    print(f"  ✓ convenience: {restored.restored_text!r}")  # noqa: T201


def test_nested_tags() -> None:
    """Вложенные теги."""
    handler = XliffTagHandler()

    text = '<g id="1"><g id="2">Deep</g> text</g>'
    result = handler.replace_tags(text)

    assert len(result.mappings) == 4  # <g1>, <g2>, </g>, </g>
    print(f"  ✓ nested replace: {result.cleaned_text!r}")  # noqa: T201

    translated = "__TAG1____TAG2__Глубоко__TAG3__ текст__TAG4__"
    restored = handler.restore_tags(translated, result.mappings, text)

    assert restored.success
    print(f"  ✓ nested restore: {restored.restored_text!r}")  # noqa: T201


def test_placeholder_aliases() -> None:
    """Модель вернула плейсхолдеры в нестандартном формате."""
    handler = XliffTagHandler()

    text = '<g id="1">Hello</g>'
    result = handler.replace_tags(text)

    for translated, fmt in [
        ("{TAG1}Привет{TAG2}", "{TAG}"),
        ("[TAG1]Привет[TAG2]", "[TAG]"),
        ("<TAG1>Привет<TAG2>", "<TAG>"),
    ]:
        restored = handler.restore_tags(translated, result.mappings, text)
        assert restored.success, f"failed for format {fmt}"
        assert '<g id="1">' in restored.restored_text, f"open tag missing for {fmt}"
        assert "</g>" in restored.restored_text, f"close tag missing for {fmt}"


def test_tag_with_attributes() -> None:
    """Теги с различными атрибутами."""
    handler = XliffTagHandler()

    text = '<mrk mtype="x-cdata" mid="42">Some code</mrk>'
    result = handler.replace_tags(text)

    assert result.has_tags
    assert len(result.mappings) == 2
    print(f"  ✓ attrs replace: {result.cleaned_text!r}")  # noqa: T201

    translated = "__TAG1__Какой-то код__TAG2__"
    restored = handler.restore_tags(translated, result.mappings, text)

    assert restored.success
    assert 'mtype="x-cdata"' in restored.restored_text
    print(f"  ✓ attrs restore: {restored.restored_text!r}")  # noqa: T201


if __name__ == "__main__":
    tests = [
        ("Basic paired tags", test_basic_paired_tags),
        ("Self-closing tags", test_self_closing_tags),
        ("bpt/ept tags", test_bpt_ept_tags),
        ("Mixed tags", test_mixed_tags),
        ("No tags", test_no_tags),
        ("Empty text", test_empty_text),
        ("Model lost tags", test_model_lost_tags),
        ("Model lost all tags", test_model_lost_all_tags),
        ("Convenience functions", test_convenience_functions),
        ("Nested tags", test_nested_tags),
        ("Tags with attributes", test_tag_with_attributes),
    ]

    passed = 0
    failed = 0
    for name, test_fn in tests:
        print(f"\n{'=' * 60}")  # noqa: T201
        print(f"TEST: {name}")  # noqa: T201
        print(f"{'=' * 60}")  # noqa: T201
        try:
            test_fn()
            passed += 1
            print("  ✅ PASSED")  # noqa: T201
        except Exception as e:
            failed += 1
            print(f"  ❌ FAILED: {e}")  # noqa: T201

    print(f"\n{'=' * 60}")  # noqa: T201
    print(f"RESULTS: {passed} passed, {failed} failed, {passed + failed} total")  # noqa: T201
    print(f"{'=' * 60}")  # noqa: T201
