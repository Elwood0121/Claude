#!/usr/bin/env python3
"""Add a public-domain book to Open Shelf.

Usage:
  python3 tools/add_book.py <gutenberg-id> <slug> "<Title>" "<Author>" <year> [--heading REGEX]

It downloads the plain-text edition from Project Gutenberg, removes the
Gutenberg header and footer, splits the text into chapters and writes
books/<slug>.txt plus an entry in books/books.json.

Book file format (kept tiny on purpose):
  # Chapter title
  One paragraph per line.
"""
import argparse, hashlib, json, re, sys, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BOOKS = ROOT / "books"

DEFAULT_HEADING = (
    r"(?:CHAPTER|Chapter|STAVE|Stave|LETTER|Letter|BOOK|Book|PART|Part)\s+[\w.:—-]+.*"
    r"|(?:[IVXLC]+\.?)(?:\s+[A-Z].*)?"
    r"|\d{1,3}\.?"
)


def fetch(gid):
    url = f"https://www.gutenberg.org/cache/epub/{gid}/pg{gid}.txt"
    with urllib.request.urlopen(url, timeout=60) as r:
        text = r.read().decode("utf-8-sig", "replace")
    if "*** START OF" not in text:
        sys.exit(f"Got something other than a Gutenberg text from {url}")
    return text


def strip_gutenberg(text):
    text = text.replace("\r\n", "\n")
    start = re.search(r"^\*\*\* ?START OF.*$", text, re.M)
    end = re.search(r"^\*\*\* ?END OF.*$", text, re.M)
    return text[start.end(): end.start() if end else None].strip()


def paragraphs(block):
    """Join hard-wrapped lines into one line per paragraph."""
    out = []
    for p in re.split(r"\n\s*\n", block):
        p = " ".join(line.strip() for line in p.split("\n")).strip()
        p = re.sub(r"\s+", " ", p).replace("_", "")
        if p:
            out.append(p)
    return out


SMALL = {"a", "an", "and", "the", "of", "in", "on", "to", "at", "by", "for", "or", "with"}


def tidy(title):
    """'CHAPTER II: THE POOL' -> 'Chapter II: The Pool' (roman numerals stay upper case)."""
    def word(w, first):
        if re.fullmatch(r"[IVXLC]+[.:]?", w):
            return w
        low = w.lower()
        return low if (low in SMALL and not first) else low[:1].upper() + low[1:]
    if title.upper() != title:
        return title.replace("CHAPTER", "Chapter")
    return " ".join(word(w, i == 0 or title.split()[i - 1].endswith(":")) for i, w in enumerate(title.split()))


def split_chapters(body, heading):
    lines = body.split("\n")
    pat = re.compile(rf"^\s*(?:{heading})\s*$")
    marks = [i for i, l in enumerate(lines) if pat.match(l) and l.strip()]
    chunks = []
    for n, i in enumerate(marks):
        j = marks[n + 1] if n + 1 < len(marks) else len(lines)
        title = lines[i].strip().rstrip(".")
        rest = lines[i + 1: j]
        # A short line right after the heading is the chapter's name ("CHAPTER I." / "Down the Rabbit-Hole").
        k = 0
        while k < len(rest) and not rest[k].strip():
            k += 1
        if k < len(rest):
            cand = rest[k].strip()
            standalone = k + 1 >= len(rest) or not rest[k + 1].strip()
            all_caps = cand.upper() == cand and any(ch.isalpha() for ch in cand)
            if standalone and len(cand) < 70 and (all_caps or not cand.endswith((".", ",", ";", "”", '"'))):
                title = f"{title}: {cand.rstrip('.')}"
                rest = rest[k + 1:]
        chunks.append([tidy(title), paragraphs("\n".join(rest))])
    # Drop table-of-contents hits: headings followed by almost no text.
    real = [c for c in chunks if sum(len(p) for p in c[1]) > 400]
    front = paragraphs("\n".join(lines[: marks[0]])) if marks else paragraphs(body)
    if not real:
        return [["Full text", front]]
    return real


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("gid"); ap.add_argument("slug"); ap.add_argument("title"); ap.add_argument("author"); ap.add_argument("year", type=int)
    ap.add_argument("--heading", default=DEFAULT_HEADING, help="regex matching a whole chapter-heading line")
    ap.add_argument("--file", help="use a local Gutenberg .txt instead of downloading")
    a = ap.parse_args()

    raw = Path(a.file).read_text("utf-8-sig") if a.file else fetch(a.gid)
    chapters = split_chapters(strip_gutenberg(raw), a.heading)
    BOOKS.mkdir(exist_ok=True)
    out = "".join(f"# {t}\n" + "\n".join(ps) + "\n" for t, ps in chapters)
    (BOOKS / f"{a.slug}.txt").write_text(out, "utf-8")

    cat_path = BOOKS / "books.json"
    cat = json.loads(cat_path.read_text()) if cat_path.exists() else []
    cat = [b for b in cat if b["id"] != a.slug]
    cat.append({
        "id": a.slug, "title": a.title, "author": a.author, "year": a.year,
        "chapters": len(chapters), "words": len(out.split()),
        "hue": int(hashlib.md5(a.slug.encode()).hexdigest(), 16) % 360,
        "gutenberg": int(a.gid),
    })
    cat.sort(key=lambda b: b["title"].removeprefix("The ").removeprefix("A "))
    cat_path.write_text(json.dumps(cat, ensure_ascii=False, separators=(",", ":")).replace("},{", "},\n{") + "\n")
    print(f"{a.title}: {len(chapters)} chapters, {len(out) // 1024} KB")
    for t, _ in chapters[:4]:
        print("  ", t)


if __name__ == "__main__":
    main()
