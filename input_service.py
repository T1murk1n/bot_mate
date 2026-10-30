"""Shared normalization and matching for user input and schedule names."""

import difflib
from datetime import date, timedelta
import re
import unicodedata


def normalize_text(value: str) -> str:
    value = unicodedata.normalize("NFKC", value)
    value = value.translate(str.maketrans("‐‑‒–—−", "------"))
    return " ".join(value.casefold().replace("ё", "е").split())


def parse_schedule_date(value: str, today: date | None = None) -> date | None:
    """None means ordinary input; ValueError means an invalid date request."""
    today = today or date.today()
    value = normalize_text(value)
    if value in {"на дату", "расписание на дату", "выбрать дату", "/date"}:
        return None
    prefix = re.match(
        r"^(?:расписание(?:\s+на)?|пары(?:\s+на)?|на\s+дату|дата|на|/date|/schedule)"
        r"(?:\s*:\s*|\s+)(.+)$",
        value,
    )
    if prefix:
        value = prefix.group(1)
    relative = {"сегодня": 0, "завтра": 1, "послезавтра": 2, "вчера": -1}
    if value in relative:
        try:
            return today + timedelta(days=relative[value])
        except OverflowError:
            raise ValueError("Эта дата выходит за допустимые границы.") from None
    iso = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", value)
    numeric = re.fullmatch(r"(\d{1,2})([./-])(\d{1,2})(?:\2(\d{4}|\d{2}))?\.?", value)
    if iso or numeric:
        if iso:
            year, month, day = map(int, iso.groups())
        else:
            day = int(numeric.group(1))
            month = int(numeric.group(3))
            year_text = numeric.group(4)
            year = today.year if year_text is None else int(year_text)
            if year_text is not None and len(year_text) == 2:
                year += 2000
        try:
            return date(year, month, day)
        except ValueError:
            raise ValueError("Такой даты нет. Введи дату в формате ДД.ММ.ГГГГ, например 05.11.2026.") from None
    if prefix or re.fullmatch(r"\d{1,4}(?:[./-]\d{0,4}){1,3}\.?", value):
        raise ValueError("Не удалось распознать дату. Введи ДД.ММ.ГГГГ или ДД.ММ, например 05.11.2026.")
    return None


def normalize_group(value: str) -> str:
    value = normalize_text(value)
    value = value.translate(str.maketrans("abcehkmoptxy", "авсенкмортху"))
    if not re.fullmatch(r"[а-яa-z0-9\s/_\\-]+", value):
        return ""
    return re.sub(r"[\s/_\\-]+", "", value)


def find_group(value: str, groups: list[str]) -> str | None:
    normalized = normalize_group(value)
    if not normalized:
        return None
    matches = [group for group in groups if normalize_group(group) == normalized]
    return matches[0] if len(matches) == 1 else None


def looks_like_group(value: str) -> bool:
    value = normalize_text(value)
    return bool(re.fullmatch(r"[а-яa-z0-9\s/_\\-]+", value) and re.search(r"\d", value))


def extract_teacher_query(value: str) -> str | None:
    """None means no teacher command; an empty string means a prompt request."""
    value = normalize_text(value)
    match = re.match(
        r"^(?:/?препод(?:а|у|ом|е|ы)?|/?преподавател(?:ь|я|ю|ем|е|и|ей)|"
        r"/teacher|фио(?:\s+преподавателя)?|фамилия)(?:\s*[:\-]\s*|\s+|$)(.*)$",
        value,
    )
    if not match:
        return None
    return re.sub(r"^по фамилии(?:\s+|$)", "", match.group(1)).strip()


def _surname_forms(surname: str, female: bool) -> set[str]:
    """Generate case forms from a known surname, keeping unrelated names apart."""
    forms = {surname}
    if surname.endswith(("ко", "их", "ых")):
        return forms
    if surname.endswith("а"):
        stem = surname[:-1]
        genitive = "и" if stem.endswith(tuple("гкхжчшщ")) else "ы"
        forms.update(stem + ending for ending in (genitive, "е", "у", "ой", "ою"))
    elif surname.endswith("я"):
        forms.update(surname[:-1] + ending for ending in ("и", "е", "ю", "ей", "ею"))
    elif not female:
        if surname.endswith(("ов", "ев", "ин", "ын")):
            forms.update(surname + ending for ending in ("а", "у", "ым", "е"))
        elif surname.endswith(("й", "ь")):
            forms.update(surname[:-1] + ending for ending in ("я", "ю", "ем", "е"))
        elif surname[-1:] in "бвгджзклмнпрстфхцчшщ":
            forms.update(surname + ending for ending in ("а", "у", "ом", "е"))
    return forms


def _name_matches(query: list[str], names: list[str]) -> bool:
    def matches(word: str, name: str) -> bool:
        return word == name or (len(word) == 1 and name.startswith(word))

    if not query:
        return True
    if len(query) == 1:
        return any(matches(query[0], name) for name in names)
    return len(query) == len(names) and all(matches(word, name) for word, name in zip(query, names))


def find_teachers(query: str, teachers: dict[str, str]) -> list[str]:
    """Match surnames, declined surnames, full names, and initials."""
    normalized = normalize_text(query)
    if re.search(r"\d", normalized):
        return []
    words = re.findall(r"[^\W\d_]+(?:-[^\W\d_]+)*", normalized)
    if not 1 <= len(words) <= 3:
        return []
    matches = []
    for full_name in dict.fromkeys(teachers.values()):
        parts = normalize_text(full_name).split()
        if len(parts) < 2:
            continue
        surname = parts[0]
        forms = _surname_forms(surname, female=parts[-1].endswith("на"))
        for index, word in enumerate(words):
            if word in forms and _name_matches(words[:index] + words[index + 1:], parts[1:]):
                matches.append(full_name)
                break
    # A case form can also be another person's surname, e.g. Богданова.
    return sorted(set(matches), key=normalize_text)


def teacher_suggestions(query: str, teachers: dict[str, str]) -> list[str]:
    words = re.findall(r"[^\W\d_]+", normalize_text(query))
    if not words:
        return []
    surnames = {normalize_text(name.split()[0]): name.split()[0] for name in teachers.values()}
    return [surnames[word] for word in difflib.get_close_matches(words[0], surnames, n=3, cutoff=0.78)]
