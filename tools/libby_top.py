#!/usr/bin/env python3
"""Save the most popular audiobooks at a Libby library to books/libby-top.json.

Usage:
  python3 tools/libby_top.py [library-code] [count]     (defaults: tblc 100)

The site links each title to that library's Libby. Nothing is hosted here:
only the title, author, cover link and Libby title id are saved. Run it again
to refresh the list.
"""
import json, sys, urllib.request
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "books" / "libby-top.json"


def main():
    lib = sys.argv[1] if len(sys.argv) > 1 else "tblc"
    count = int(sys.argv[2]) if len(sys.argv) > 2 else 100
    items, page = [], 1
    while len(items) < count:
        url = (f"https://thunder.api.overdrive.com/v2/libraries/{lib}/media"
               f"?format=audiobook-overdrive,audiobook-mp3&sort=popularity&perPage=50&page={page}")
        with urllib.request.urlopen(url, timeout=60) as r:
            batch = json.load(r).get("items", [])
        if not batch:
            break
        items += batch
        page += 1
    out = []
    for it in items[:count]:
        covers = it.get("covers") or {}
        cover = (covers.get("cover300Wide") or covers.get("cover150Wide") or {}).get("href", "")
        out.append({"id": it["id"], "t": it["title"], "a": it.get("firstCreatorName", ""), "c": cover})
    OUT.write_text(json.dumps({"library": lib, "items": out}, ensure_ascii=False, separators=(",", ":")).replace('},{', '},\n{') + "\n")
    print(f"Saved {len(out)} titles from {lib} to {OUT.name}")
    for x in out[:5]:
        print("  ", x["t"], "—", x["a"])


if __name__ == "__main__":
    main()
