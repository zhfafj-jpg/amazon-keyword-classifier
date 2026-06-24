from __future__ import annotations

from .utils import compact_join, contains_term


def translate_keyword(keyword: str, translation_terms: dict[str, str]) -> tuple[str, str]:
    hits: list[tuple[str, str]] = []
    for term, translation in sorted(translation_terms.items(), key=lambda item: len(item[0]), reverse=True):
        if contains_term(keyword, term):
            hits.append((term, translation))

    translations: list[str] = []
    used_translations: set[str] = set()
    for _, translation in hits:
        if translation not in used_translations:
            translations.append(translation)
            used_translations.add(translation)

    if not translations:
        return keyword, "待人工确认"

    note = "部分词待人工确认" if len(" ".join(term for term, _ in hits).split()) < max(1, len(keyword.split()) // 2) else ""
    return compact_join(translations, " / "), note
