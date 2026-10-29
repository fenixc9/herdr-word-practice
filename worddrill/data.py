"""Word model and wordbook loading.

Bundled books are compact TSV files under ``data/wordbooks``. Custom books are
JSON or CSV files imported into the plugin state directory.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
BUNDLED_DIR = PLUGIN_ROOT / "data" / "wordbooks"
BOOK_ORDER = ("cet4", "cet6", "coding")


class WordbookError(ValueError):
    """Raised when a wordbook file is missing or malformed."""


@dataclass(frozen=True)
class Word:
    key: str
    book: str
    word: str
    ipa: str
    pos: str
    cn: str
    en: str
    zh: str
    syn: tuple[str, ...] = field(default_factory=tuple)
    root: str = ""
    phr: tuple[str, ...] = field(default_factory=tuple)
    # Extra examples beyond the primary ``en``/``zh`` pair, shortest first.
    extra_examples: tuple[tuple[str, str], ...] = field(default_factory=tuple)

    @property
    def examples(self) -> tuple[tuple[str, str], ...]:
        """All examples for this word, primary one first."""
        primary = ((self.en, self.zh),) if self.en else ()
        return primary + self.extra_examples

    @property
    def length_hint(self) -> str:
        return " ".join("_" if ch.isalpha() else ch for ch in self.word)

    def blanked_example(self) -> str:
        if not self.en:
            return ""
        lowered = self.en.lower()
        target = self.word.lower()
        idx = lowered.find(target)
        if idx < 0:
            return self.en
        return self.en[:idx] + "______" + self.en[idx + len(self.word):]

    def to_dict(self) -> dict:
        data = {"w": self.word, "ipa": self.ipa, "pos": self.pos,
                "cn": self.cn, "en": self.en, "zh": self.zh}
        if self.syn:
            data["syn"] = list(self.syn)
        if self.root:
            data["root"] = self.root
        if self.phr:
            data["phr"] = list(self.phr)
        if self.extra_examples:
            data["ex"] = [f"{en} :: {zh}" if zh else en
                          for en, zh in self.extra_examples]
        return data


@dataclass(frozen=True)
class Wordbook:
    id: str
    name: str
    name_en: str
    description: str
    words: tuple[Word, ...]
    path: Path | None = None
    custom: bool = False

    def __len__(self) -> int:
        return len(self.words)

    @property
    def label(self) -> str:
        if self.name_en and self.name_en != self.name:
            return f"{self.name} · {self.name_en}"
        return self.name


# Hand-written wordbooks are friendlier with long keys, so accept both the
# compact on-disk names and readable aliases.
JSON_ALIASES = {
    "w": ("w", "word", "english"),
    "cn": ("cn", "meaning", "zh_meaning", "translation"),
    "en": ("en", "example", "sentence"),
    "zh": ("zh", "example_zh", "example_translation"),
    "phr": ("phr", "phrases", "collocations"),
}


def _pick(raw: dict, name: str) -> object:
    for candidate in JSON_ALIASES.get(name, (name,)):
        if raw.get(candidate) not in (None, ""):
            return raw[candidate]
    return raw.get(name)


def _require_str(raw: dict, name: str, where: str) -> str:
    value = _pick(raw, name)
    if not isinstance(value, str) or not value.strip():
        raise WordbookError(f"{where}: missing or empty '{name}'")
    return value.strip()


def _optional_str(raw: dict, name: str) -> str:
    value = _pick(raw, name)
    return value.strip() if isinstance(value, str) else ""


def _string_list(raw: dict, name: str, where: str) -> tuple[str, ...]:
    value = _pick(raw, name) or []
    if isinstance(value, str):
        value = [part for part in value.split(",")]
    if not isinstance(value, list):
        raise WordbookError(f"{where}: '{name}' must be a list of strings")
    return tuple(str(item).strip() for item in value if str(item).strip())


def _parse_word_json(raw: object, book_id: str, where: str) -> Word:
    if not isinstance(raw, dict):
        raise WordbookError(f"{where}: each word must be an object")
    word = _require_str(raw, "w", where)
    syn = _string_list(raw, "syn", where)
    phr = _string_list(raw, "phr", where)
    return Word(
        key=f"{book_id}:{word.lower()}",
        book=book_id,
        word=word,
        ipa=str(raw.get("ipa") or "").strip(),
        pos=str(raw.get("pos") or "").strip(),
        cn=_require_str(raw, "cn", where),
        en=_optional_str(raw, "en"),
        zh=_optional_str(raw, "zh"),
        syn=syn,
        root=str(raw.get("root") or "").strip(),
        phr=phr,
    )


def parse_book(raw: object, path: Path | None = None, custom: bool = False) -> Wordbook:
    where = str(path or "<memory>")
    if not isinstance(raw, dict):
        raise WordbookError(f"{where}: wordbook must be an object")
    book_id = _require_str(raw, "id", where)
    if not all(ch.isalnum() or ch in "._-" for ch in book_id):
        raise WordbookError(f"{where}: invalid book id '{book_id}'")
    words_raw = raw.get("words")
    if not isinstance(words_raw, list) or not words_raw:
        raise WordbookError(f"{where}: 'words' must be a non-empty list")
    words: list[Word] = []
    seen: set[str] = set()
    for index, item in enumerate(words_raw):
        word = _parse_word_json(item, book_id, f"{where} word #{index + 1}")
        if word.key in seen:
            raise WordbookError(f"{where} word #{index + 1}: duplicate '{word.word}'")
        seen.add(word.key)
        words.append(word)
    return Wordbook(
        id=book_id,
        name=str(raw.get("name") or book_id),
        name_en=str(raw.get("name_en") or ""),
        description=str(raw.get("description") or ""),
        words=tuple(words),
        path=path,
        custom=custom,
    )


TSV_COLUMNS = ("w", "ipa", "pos", "cn", "en", "zh", "syn", "root", "phr")


def parse_tsv(text: str, path: Path) -> Wordbook:
    """Parse the compact bundled format.

    Leading ``# key=value`` lines carry book metadata; the rest is one word per
    line with tab-separated columns.
    """
    meta: dict[str, str] = {}
    words: list[Word] = []
    seen: set[str] = set()
    book_id = path.stem
    for line_no, line in enumerate(text.splitlines(), start=1):
        if not line.strip() or line.lstrip().startswith("//"):
            continue
        if line.startswith("#"):
            body = line[1:].strip()
            if "=" in body:
                key, _, value = body.partition("=")
                meta[key.strip()] = value.strip()
            continue
        parts = line.split("\t")
        parts += [""] * (len(TSV_COLUMNS) - len(parts))
        raw = dict(zip(TSV_COLUMNS, parts[: len(TSV_COLUMNS)]))
        if not raw["w"].strip():
            continue
        word = _parse_word_json({
            "w": raw["w"].strip(),
            "ipa": raw["ipa"].strip(),
            "pos": raw["pos"].strip(),
            "cn": raw["cn"].strip(),
            "en": raw["en"].strip(),
            "zh": raw["zh"].strip(),
            "syn": [part.strip() for part in raw["syn"].split(",") if part.strip()],
            "root": raw["root"].strip(),
            "phr": [part.strip() for part in raw["phr"].split(",") if part.strip()],
        }, book_id, f"{path} line {line_no}")
        if word.key in seen:
            raise WordbookError(f"{path} line {line_no}: duplicate '{word.word}'")
        seen.add(word.key)
        words.append(word)
    if not words:
        raise WordbookError(f"{path}: no words found")
    return Wordbook(
        id=meta.get("id", book_id),
        name=meta.get("name", book_id),
        name_en=meta.get("name_en", ""),
        description=meta.get("description", ""),
        words=tuple(words),
        path=path,
    )


EXAMPLES_SUFFIX = ".examples.tsv"


def _split_example(text: str) -> tuple[str, str]:
    """Parse ``english :: 中文`` (the Chinese half is optional)."""
    english, _, chinese = text.partition("::")
    return english.strip(), chinese.strip()


def load_examples(path: Path) -> dict[str, tuple[tuple[str, str], ...]]:
    """Read a sidecar file of extra examples keyed by word.

    Keeping these out of the main wordbooks means examples can grow over time
    without rewriting (or re-reviewing) a 70 KB data file.
    """
    table: dict[str, tuple[tuple[str, str], ...]] = {}
    if not path.is_file():
        return table
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        parts = [part for part in line.split("\t") if part.strip()]
        if len(parts) < 2:
            raise WordbookError(f"{path} line {line_no}: need word + at least one example")
        word = parts[0].strip().lower()
        examples = tuple(_split_example(part) for part in parts[1:])
        table[word] = table.get(word, ()) + examples
    return table


def _normalize_example(text: str) -> str:
    return " ".join(text.lower().split()).rstrip(".")


def _attach_examples(book: Wordbook) -> Wordbook:
    """Merge the sidecar examples into a freshly loaded book."""
    sidecar = book.path.with_name(book.path.stem + EXAMPLES_SUFFIX)
    table = load_examples(sidecar)
    if not table:
        return book
    merged = []
    for word in book.words:
        extra = table.get(word.word.lower())
        if not extra:
            merged.append(word)
            continue
        seen = {_normalize_example(word.en)}
        primary = _normalize_example(word.en)
        unique = []
        for english, chinese in extra:
            key = _normalize_example(english)
            if not key or key in seen:
                continue        # the sidecar often repeats the primary sentence
            if primary and key.startswith(primary):
                # "Primary sentence, plus a clause" is not a second example: it
                # spends a screen line saying what the reader already read.
                continue
            seen.add(key)
            unique.append((english, chinese))
        merged.append(replace(word, extra_examples=tuple(unique)))
    return replace(book, words=tuple(merged))


def load_book(path: Path, custom: bool = False) -> Wordbook:
    try:
        text = Path(path).read_text(encoding="utf-8")
    except FileNotFoundError:
        raise WordbookError(f"wordbook not found: {path}") from None
    if Path(path).suffix.lower() in {".tsv", ".txt"}:
        book = parse_tsv(text, Path(path))
        return _attach_examples(Wordbook(**{**book.__dict__, "custom": custom}))
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        raise WordbookError(f"{path}: invalid JSON ({exc})") from None
    return _attach_examples(parse_book(raw, path=Path(path), custom=custom))


def custom_books_dir(state_dir: Path) -> Path:
    return Path(state_dir) / "books"


def available_books(state_dir: Path | None = None) -> list[Wordbook]:
    books: dict[str, Wordbook] = {}
    if BUNDLED_DIR.is_dir():
        for path in sorted(BUNDLED_DIR.glob("*.tsv")):
            if path.name.endswith(EXAMPLES_SUFFIX):
                continue        # sidecar example data, not a wordbook
            book = load_book(path)
            books[book.id] = book
        for path in sorted(BUNDLED_DIR.glob("*.json")):
            book = load_book(path)
            books[book.id] = book
    if state_dir is not None:
        directory = custom_books_dir(state_dir)
        if directory.is_dir():
            for path in sorted(directory.glob("*.json")):
                try:
                    book = load_book(path, custom=True)
                except WordbookError:
                    continue
                books[book.id] = book
    ordered: list[Wordbook] = []
    for book_id in BOOK_ORDER:
        if book_id in books:
            ordered.append(books.pop(book_id))
    ordered.extend(sorted(books.values(), key=lambda b: (not b.custom, b.name)))
    return ordered


def find_book(book_id: str, state_dir: Path | None = None) -> Wordbook:
    for book in available_books(state_dir):
        if book.id == book_id:
            return book
    ids = ", ".join(b.id for b in available_books(state_dir)) or "<none>"
    raise WordbookError(f"unknown wordbook '{book_id}' (available: {ids})")


def import_book(source: Path, state_dir: Path, book_id: str | None = None,
                name: str | None = None) -> Wordbook:
    source = Path(source)
    if not source.is_file():
        raise WordbookError(f"import source not found: {source}")
    text = source.read_text(encoding="utf-8")
    if source.suffix.lower() in {".csv", ".tsv", ".txt"}:
        if source.suffix.lower() == ".tsv" and text.lstrip().startswith("#"):
            book = parse_tsv(text, source)
            raw = {
                "id": book_id or book.id,
                "name": name or book.name,
                "name_en": book.name_en,
                "description": book.description,
                "words": [w.to_dict() for w in book.words],
            }
        else:
            raw = _book_from_table(text, source, book_id, name)
    else:
        try:
            raw = json.loads(text)
        except json.JSONDecodeError as exc:
            raise WordbookError(f"{source}: invalid JSON ({exc})") from None
        if not isinstance(raw, dict):
            raise WordbookError(f"{source}: expected a JSON object")
        if book_id:
            raw["id"] = book_id
        if name:
            raw["name"] = name
    if not raw.get("id"):
        raise WordbookError("wordbook needs an 'id' or pass --book-id")
    book = parse_book(raw, path=source, custom=True)
    target_dir = custom_books_dir(state_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{book.id}.json"
    payload = {
        "id": book.id, "name": book.name, "name_en": book.name_en,
        "description": book.description, "words": [w.to_dict() for w in book.words],
    }
    from .store import atomic_write_json

    atomic_write_json(target, payload)
    return load_book(target, custom=True)


def _book_from_table(text: str, source: Path, book_id: str | None,
                     name: str | None) -> dict:
    rows = [line for line in text.splitlines() if line.strip()]
    if not rows:
        raise WordbookError(f"{source}: file is empty")
    delimiter = "\t" if "\t" in rows[0] else ","
    header = [part.strip().lower() for part in rows[0].split(delimiter)]
    has_header = "word" in header or "w" in header
    columns = header if has_header else ["word", "meaning"]
    data_rows = rows[1:] if has_header else rows
    words = []
    for line in data_rows:
        parts = [part.strip() for part in line.split(delimiter)]
        record = dict(zip(columns, parts))
        word = record.get("word") or record.get("w") or (parts[0] if parts else "")
        meaning = (record.get("meaning") or record.get("cn")
                   or record.get("translation") or (parts[1] if len(parts) > 1 else ""))
        if not word:
            continue
        words.append({
            "w": word,
            "ipa": record.get("ipa", ""),
            "pos": record.get("pos", ""),
            "cn": meaning,
            "en": record.get("en") or record.get("example", ""),
            "zh": record.get("zh") or record.get("example_zh", ""),
        })
    if not words:
        raise WordbookError(f"{source}: no words found")
    return {
        "id": book_id or source.stem.lower().replace(" ", "-"),
        "name": name or source.stem,
        "name_en": "",
        "description": f"Imported from {source.name}",
        "words": words,
    }
