#!/usr/bin/env python3
"""把公开的四六级大纲词表转换成 word-practice 的词书格式。

用法::

    python3 scripts/fetch-wordlists.py            # 下载并生成 cet4 / cet6
    python3 scripts/fetch-wordlists.py --check     # 只看会生成什么，不写文件

数据源（MIT，仓库里带中文释义 + 音标）：

    https://github.com/mahavivo/english-wordlists

生成两个文件：``data/wordbooks/cet4.tsv`` 和 ``data/wordbooks/cet6.tsv``，
每行 ``word \\t ipa \\t pos \\t 中文释义``。已经手写过的词（音标、词性、例句、
近义词、搭配）会被保留并覆盖到新数据上，所以重跑不会丢掉精修过的内容。
手写内容保存在 ``data/wordbooks/curated/*.tsv``。
"""

from __future__ import annotations

import argparse
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BOOKS = ROOT / "data" / "wordbooks"
CURATED = BOOKS / "curated"

SOURCES = {
    "cet4": ("https://raw.githubusercontent.com/mahavivo/english-wordlists/master/"
             "CET4_edited.txt", "CET-4 核心", "大学英语四级大纲词表（4615 词）"),
    "cet6": ("https://raw.githubusercontent.com/mahavivo/english-wordlists/master/"
             "CET6_edited.txt", "CET-6 进阶", "大学英语六级大纲词表（约 2000 词）"),
}

# ``word [ipa] pos.释义`` — split on the bracketed phonetics instead of trying
# to match the word first (a non-greedy word pattern happily matches "a").
BRACKETED = re.compile(r"^(?P<head>[^\[]*)\[(?P<ipa>[^\]]*)\](?P<tail>.*)$")
PLAIN = re.compile(r"^(?P<head>[A-Za-z][A-Za-z\-' ]*)\s+(?P<tail>.*)$")
# "vt.丢弃" / "prep 在…之中" / "a.不正常的" — the dot is optional in the source.
POS = re.compile(r"^((?:[a-z]{1,5}\.){1,3}|(?:[a-z]{1,5})(?=\s))")


def fetch(url: str) -> str:
    with urllib.request.urlopen(url, timeout=30) as response:
        return response.read().decode("utf-8-sig", "replace")


def parse(text: str) -> list[tuple[str, str, str, str]]:
    """Return (word, ipa, pos, meaning) rows."""
    rows: list[tuple[str, str, str, str]] = []
    seen: set[str] = set()
    for line in text.splitlines():
        line = line.strip().replace("\r", "")
        if not line or line.startswith(("(", "大学英语", "英语")):
            continue
        if len(line) == 1:                     # the A/B/C section headers
            continue
        match = BRACKETED.match(line)
        if match:
            word = match.group("head").strip()
            ipa = match.group("ipa").strip()
            rest = match.group("tail").strip()
        else:
            match = PLAIN.match(line)
            if not match:
                continue
            word, ipa, rest = match.group("head").strip(), "", match.group("tail").strip()
        if not word or len(word.split()) > 3 or not re.match(r"^[A-Za-z\-']", word):
            continue
        pos = ""
        pos_match = POS.match(rest)
        if pos_match:
            pos = pos_match.group(1).strip()
            if not pos.endswith("."):
                pos += "."          # normalise "prep 在…" to "prep."
            rest = rest[len(pos_match.group(1)):].strip()
        if not rest or not re.search(r"[\u4e00-\u9fff]", rest):
            continue                            # no Chinese gloss, skip
        key = word.lower()
        if key in seen:
            continue
        seen.add(key)
        rows.append((word, ipa, pos, rest.replace("\t", " ")))
    return rows


def curated_index(book_id: str) -> dict[str, list[str]]:
    """Existing hand-written columns, keyed by word."""
    path = CURATED / f"{book_id}.tsv"
    table: dict[str, list[str]] = {}
    if not path.is_file():
        return table
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        parts = line.split("\t")
        parts += [""] * (9 - len(parts))
        table[parts[0].strip().lower()] = parts
    return table


def build(book_id: str, url: str, name: str, description: str,
          rows: list[tuple[str, str, str, str]]) -> str:
    curated = curated_index(book_id)
    lines = [f"# id={book_id}", f"# name={name}", "# name_en=",
             f"# description={description}"]
    kept = 0
    for word, ipa, pos, meaning in rows:
        old = curated.get(word.lower())
        if old:
            kept += 1
            ipa = old[1] or ipa
            pos = old[2] or pos
            meaning = old[3] or meaning
            extra = old[4:] + [""] * (9 - len(old))
            lines.append("\t".join([word, ipa, pos, meaning, *extra])[:0] or
                         "\t".join([word, ipa, pos, meaning] + extra[:5]))
        else:
            lines.append("\t".join([word, ipa, pos, meaning, "", "", "", "", ""]))
    print(f"  {book_id}: {len(rows)} 词（其中 {kept} 个保留了手写的例句/近义/搭配）")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="只报告不写文件")
    parser.add_argument("--book", choices=sorted(SOURCES), action="append",
                        help="只处理某一本（可重复）")
    args = parser.parse_args(argv)

    chosen = args.book or sorted(SOURCES)
    for book_id in chosen:
        url, name, description = SOURCES[book_id]
        print(f"下载 {book_id} …")
        text = fetch(url)
        rows = parse(text)
        if len(rows) < 100:
            print(f"  !! 只解析出 {len(rows)} 词，格式可能变了，已跳过", file=sys.stderr)
            continue
        payload = build(book_id, url, name, description, rows)
        target = BOOKS / f"{book_id}.tsv"
        if args.check:
            print(f"  （check 模式）会写入 {target}，{len(payload.splitlines())} 行")
        else:
            target.write_text(payload, encoding="utf-8")
            print(f"  写入 {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
