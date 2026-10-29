import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from worddrill import data  # noqa: E402

BOOKS = ("cet4", "cet6", "coding")


@pytest.mark.parametrize("book_id", BOOKS)
def test_bundled_books_load(book_id):
    book = data.load_book(ROOT / "data" / "wordbooks" / f"{book_id}.tsv")
    assert book.id == book_id
    assert len(book) >= 250
    assert book.name and book.description
    keys = [word.key for word in book.words]
    assert len(keys) == len(set(keys)), "duplicate keys in book"
    for word in book.words:
        assert word.word.strip(), "empty word"
        assert word.cn.strip(), f"{word.word} missing Chinese gloss"
        if word.en:
            assert word.zh, f"{word.word} has an example without translation"

    # Example sentences are hand-written, so only a slice of a full syllabus
    # wordlist carries them; the curated words must keep theirs.
    with_example = [word for word in book.words if word.en]
    assert len(with_example) >= min(200, len(book.words) // 4), \
        f"{book_id}: only {len(with_example)} words have examples"


def test_available_books_order_and_ids():
    books = data.available_books()
    assert [book.id for book in books] == list(BOOKS)
    assert sum(len(book) for book in books) > 1000


def test_find_book_error_lists_choices():
    with pytest.raises(data.WordbookError) as error:
        data.find_book("nope")
    assert "cet4" in str(error.value)


def test_length_hint_keeps_spaces_and_hyphens():
    word = data.Word("t", "b", "re-run", "", "", "", "", "", "")
    assert word.length_hint == "_ _ - _ _ _"
    assert data.Word("t", "b", "go", "", "", "", "", "", "").length_hint == "_ _"


def test_blanked_example_hides_the_word():
    word = data.Word(key="t", book="b", word="cache", ipa="", pos="v.",
                     cn="缓存", en="The cache hides latency.", zh="缓存隐藏了延迟。")
    blanked = word.blanked_example()
    assert "cache" not in blanked.lower()
    assert "_" in blanked


def test_blanked_example_falls_back_when_word_absent():
    word = data.Word(key="t", book="b", word="cache", ipa="", pos="v.",
                     cn="缓存", en="Nothing to see.", zh="没什么可看的。")
    assert word.blanked_example() == "Nothing to see."


def test_parse_tsv_rejects_duplicates(tmp_path):
    text = "# id=x\nword\t\tv.\t一件\nword\t\tv.\t重复\n"
    with pytest.raises(data.WordbookError) as error:
        data.parse_tsv(text, tmp_path / "x.tsv")
    assert "duplicate" in str(error.value).lower()


def test_parse_tsv_requires_meaning(tmp_path):
    text = "# id=x\nword\t\tv.\n"
    with pytest.raises(data.WordbookError):
        data.parse_tsv(text, tmp_path / "x.tsv")


def test_import_book_from_json(tmp_path):
    source = tmp_path / "mine.json"
    source.write_text(json.dumps({
        "id": "mine",
        "name": "我的词表",
        "words": [
            {"word": "deploy", "cn": "部署"},
            {"word": "rollback", "cn": "回滚", "en": "Keep a rollback ready."},
        ],
    }, ensure_ascii=False), encoding="utf-8")
    book = data.import_book(source, tmp_path / "state", book_id="mine")
    assert book.id == "mine"
    assert [word.word for word in book.words] == ["deploy", "rollback"]
    saved = tmp_path / "state" / "books" / "mine.json"
    assert saved.is_file()
    assert data.find_book("mine", tmp_path / "state").name == "我的词表"


def test_import_book_from_csv(tmp_path):
    source = tmp_path / "words.csv"
    source.write_text("word,meaning\ncache,缓存\nschema,表结构\n", encoding="utf-8")
    book = data.import_book(source, tmp_path / "state")
    assert [word.word for word in book.words] == ["cache", "schema"]
    assert book.words[0].cn == "缓存"


def test_import_book_missing_file(tmp_path):
    with pytest.raises(data.WordbookError):
        data.import_book(tmp_path / "nope.csv", tmp_path / "state")


def test_phrases_and_roots_are_parsed():
    coding = data.find_book("coding")
    with_phr = [w for w in coding.words if w.phr]
    with_root = [w for w in coding.words if w.root]
    assert len(with_phr) > 200, "most coding words should carry collocations"
    assert len(with_root) > 80
    deploy = next(w for w in coding.words if w.word == "deploy")
    assert "deploy to production" in deploy.phr


def test_phrases_roundtrip_through_json(tmp_path):
    source = tmp_path / "mine.json"
    source.write_text(json.dumps({
        "id": "mine", "name": "短语表",
        "words": [{"w": "cache", "cn": "缓存",
                   "phrases": ["cache hit", "cache miss"],
                   "root": "cacher（藏）"}],
    }, ensure_ascii=False), encoding="utf-8")
    book = data.import_book(source, tmp_path / "state")
    word = book.words[0]
    assert word.phr == ("cache hit", "cache miss")
    assert word.root == "cacher（藏）"


def test_tsv_ninth_column_is_phrases(tmp_path):
    text = ("# id=x\n"
            "cache\t/kæʃ/\tn.\t缓存\tthe cache\t缓存\tstore\tcach\tcache hit,cache miss\n")
    book = data.parse_tsv(text, tmp_path / "x.tsv")
    assert book.words[0].phr == ("cache hit", "cache miss")


def test_multiple_examples_are_loaded_and_ordered():
    coding = data.find_book("coding")
    word = next(w for w in coding.words if w.word == "typo")
    assert len(word.examples) >= 2, "coding words should carry several examples"
    assert word.examples[0] == (word.en, word.zh)
    lengths = [len(en.split()) for en, _ in word.examples]
    assert max(lengths) > min(lengths), "examples should vary in length"


def test_sidecar_examples_are_deduped_against_the_primary(tmp_path):
    book = tmp_path / "x.tsv"
    book.write_text("# id=x\ncache\t\tv.\t缓存\tThe cache hides latency.\t缓存隐藏了延迟。\n",
                    encoding="utf-8")
    (tmp_path / "x.examples.tsv").write_text(
        "cache\tThe cache hides latency. :: 缓存隐藏了延迟。\n"          # exact repeat
        "cache\tThe cache hides latency, and it does so quietly. :: 重复。\n"  # extension
        "cache\tA cold cache made the first request of the day slow. :: 冷缓存让当天第一个请求变慢。\n",
        encoding="utf-8")
    loaded = data.load_book(book)
    word = loaded.words[0]
    assert [en for en, _ in word.examples] == [
        "The cache hides latency.",
        "A cold cache made the first request of the day slow.",
    ]


def test_examples_sidecar_is_not_treated_as_a_wordbook():
    ids = [book.id for book in data.available_books()]
    assert not [book_id for book_id in ids if "examples" in book_id]
