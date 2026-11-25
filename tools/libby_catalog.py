#!/usr/bin/env python3
"""Save every audiobook at a Libby library to books/libby.json, with categories.

Usage:
  python3 tools/libby_catalog.py [library-code]      (default: tblc)

The site lets you search and filter this list and opens each title in that
library's Libby. Nothing is hosted here: only titles, authors, categories,
cover links and Libby title ids. Run it again to refresh.

Compact format:
  {"library": "tblc", "updated": "YYYY-MM-DD",
   "subjects": {"57": "Mystery", ...},
   "items": [[id, title, author, cover, [subject ids], minutes], ...]}   (most popular first)
  cover is the part of the OverDrive cover URL after "https://img1.od-cdn.com/ImageType-150/".
"""
import datetime, json, re, sys, time, urllib.request
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "books" / "libby.json"


def minutes(it):
    for f in it.get("formats", []):
        d = f.get("duration")
        if d and re.fullmatch(r"\d+:\d\d:\d\d", d):
            h, m, s = map(int, d.split(":"))
            return h * 60 + m
    return 0


def main():
    lib = sys.argv[1] if len(sys.argv) > 1 else "tblc"
    subjects, items, page = {}, [], 1
    while True:
        url = (f"https://thunder.api.overdrive.com/v2/libraries/{lib}/media"
               f"?format=audiobook-overdrive,audiobook-mp3&sort=popularity&perPage=100&page={page}")
        for attempt in range(4):
            try:
                with urllib.request.urlopen(url, timeout=60) as r:
                    data = json.load(r)
                break
            except Exception:
                time.sleep(2 * (attempt + 1))
        else:
            sys.exit(f"Could not read page {page}")
        batch = data.get("items", [])
        if not batch:
            break
        for it in batch:
            cov = ((it.get("covers") or {}).get("cover150Wide") or {}).get("href", "")
            cov = re.sub(r"^https://img\d\.od-cdn\.com/ImageType-150/", "", cov)
            subs = []
            for s in it.get("subjects", []):
                subjects[s["id"]] = s["name"]
                subs.append(int(s["id"]))
            items.append([int(it["id"]), it["title"], it.get("firstCreatorName", ""), cov, subs, minutes(it)])
        print(f"page {page}: {len(items)} of {data.get('totalItems')}", flush=True)
        page += 1
        time.sleep(0.3)
    seen, unique = set(), []
    for x in items:
        if x[0] not in seen:
            seen.add(x[0]); unique.append(x)
    out = {"library": lib, "updated": datetime.date.today().isoformat(),
           "subjects": dict(sorted(subjects.items(), key=lambda kv: kv[1])), "items": unique}
    OUT.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")).replace("],[", "],\n[") + "\n")
    print(f"Saved {len(unique)} audiobooks in {len(subjects)} categories to {OUT.name} ({OUT.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
