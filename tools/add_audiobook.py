#!/usr/bin/env python3
"""Add a free LibriVox audiobook to Open Shelf.

Usage:
  python3 tools/add_audiobook.py <archive.org identifier> <slug> "<Title>" "<Author>" <year>

Find identifiers by searching the "librivoxaudio" collection on archive.org.
Only the chapter list goes into books/books.json; the audio itself streams
from archive.org, so each book adds just a few KB to the site.
"""
import hashlib, html, json, re, sys, urllib.request
from pathlib import Path

CATALOG = Path(__file__).resolve().parent.parent / "books" / "books.json"


def seconds(v):
    if v is None:
        return 0
    v = str(v)
    if ":" in v:
        s = 0
        for part in v.split(":"):
            s = s * 60 + float(part)
        return round(s)
    return round(float(v))


def main():
    if len(sys.argv) != 6:
        sys.exit(__doc__)
    ia, slug, title, author, year = sys.argv[1:]
    with urllib.request.urlopen(f"https://archive.org/metadata/{ia}", timeout=60) as r:
        meta = json.load(r)
    if not meta.get("files"):
        sys.exit(f"No files found for {ia}")

    mp3 = [f for f in meta["files"] if f["name"].endswith("_64kb.mp3")] or \
          [f for f in meta["files"] if f["name"].endswith(".mp3")]

    def track(f):
        t = str(f.get("track", "")).split("/")[0]
        return int(t) if t.isdigit() else None

    def natural(name):
        return [int(p) if p.isdigit() else p for p in re.split(r"(\d+)", name)]

    if all(track(f) is not None for f in mp3):
        mp3.sort(key=lambda f: (track(f), natural(f["name"])))
    else:
        mp3.sort(key=lambda f: natural(f["name"]))

    chapters = []
    for i, f in enumerate(mp3, 1):
        name = (f.get("title") or "").strip()
        stem = f["name"].rsplit(".", 1)[0].replace("_64kb", "")
        if not name or name == stem or re.fullmatch(r"[\w-]+", name) and "_" in name:
            name = f"Chapter {i}"
        name = re.sub(rf"^{re.escape(title)}\s*[-:–]\s*", "", name, flags=re.I)
        name = re.sub(r"^\d+\s*[-.–:]\s*(?=\S)", "", name).strip()
        chapters.append([name, f["name"], seconds(f.get("length"))])

    desc = html.unescape(re.sub(r"<[^>]+>", " ", str(meta["metadata"].get("description", ""))))
    m = re.search(r"[Rr]ead by:?\s+([A-Z][^.\n<(]{2,60})", desc)
    reader = m.group(1).strip() if m else "LibriVox volunteers"

    cat = json.loads(CATALOG.read_text()) if CATALOG.exists() else []
    cat = [b for b in cat if b["id"] != slug]
    cat.append({
        "id": slug, "title": title, "author": author, "year": int(year), "reader": reader, "ia": ia,
        "hue": int(hashlib.md5(slug.encode()).hexdigest(), 16) % 360, "ch": chapters,
    })
    cat.sort(key=lambda b: re.sub(r"^(The|A|An) ", "", b["title"]))
    CATALOG.parent.mkdir(exist_ok=True)
    CATALOG.write_text("[\n" + ",\n".join(json.dumps(b, ensure_ascii=False, separators=(",", ":")) for b in cat) + "\n]\n")
    total = sum(c[2] for c in chapters)
    print(f"{title}: {len(chapters)} chapters, {total // 3600}h {total % 3600 // 60}m, read by {reader}")
    for c in chapters[:3]:
        print("   ", c)


if __name__ == "__main__":
    main()
