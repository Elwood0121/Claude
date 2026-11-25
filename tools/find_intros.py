#!/usr/bin/env python3
"""Find where the spoken LibriVox notice ends in each chapter.

Every LibriVox file opens with "This is a LibriVox recording. All LibriVox
recordings are in the public domain. For more information, or to volunteer,
please visit librivox.org." This script listens to the first minute of each
chapter with an offline speech recognizer (Vosk), finds the end of
"librivox dot org", and stores that point (in seconds) as the 4th value of
each chapter in books/books.json. The player starts chapters there.

Needs: ffmpeg, the `vosk` Python package and a Vosk English model folder.
  python3 tools/find_intros.py --model /path/to/vosk-model-small-en-us-0.15 [book-id ...]
"""
import argparse, json, subprocess, sys, urllib.request
from pathlib import Path

CATALOG = Path(__file__).resolve().parent.parent / "books" / "books.json"
CACHE = Path.home() / ".cache" / "openshelf-intros"  # what the recognizer heard, so reruns skip the download
LISTEN = 75  # seconds of audio to scan
ANNOUNCE = {"chapter", "chapters", "stave", "letter", "adventure", "book", "part", "section", "introduction", "preface", "conclusion", "prologue", "epilogue"}


def pcm(url):
    data = subprocess.run(["curl", "-sSL", "-m", "120", "-r", f"0-{LISTEN * 8000 + 60000}", url], capture_output=True, check=True).stdout
    return subprocess.run(["ffmpeg", "-loglevel", "quiet", "-i", "pipe:0", "-t", str(LISTEN), "-ac", "1", "-ar", "16000", "-f", "s16le", "pipe:1"],
                          input=data, capture_output=True).stdout


def words(model, audio):
    from vosk import KaldiRecognizer
    rec = KaldiRecognizer(model, 16000)
    rec.SetWords(True)
    out = []
    for i in range(0, len(audio), 32000):
        if rec.AcceptWaveform(audio[i:i + 32000]):
            out += json.loads(rec.Result()).get("result", [])
    out += json.loads(rec.FinalResult()).get("result", [])
    return out


def intro_end(ws):
    """Return the time to start playback, or 0 if no notice was heard.

    Long notice:  "This is a LibriVox recording. All LibriVox recordings are in the public domain.
                   For more information, or to volunteer, please visit librivox.org."
    Short notice: "This LibriVox recording is in the public domain."
    The recognizer often mishears "LibriVox", so this keys on "domain", "visit" and "org".
    """
    text = [w["word"] for w in ws]
    d = next((i for i, w in enumerate(text) if w == "domain" and ws[i]["start"] < 50), None)
    if d is None:
        d = next((i for i, w in enumerate(text) if w == "org" and ws[i]["start"] < 50
                  and any(t in ("recording", "recordings", "volunteer", "visit") for t in text[max(0, i - 30):i])), None)
        if d is None:
            return 0
    end = d
    # Follow on through "...please visit librivox dot org" (and a spelled-out repeat of the address).
    for j in range(d + 1, len(ws)):
        if ws[j]["start"] > ws[end]["end"] + 8:
            break
        if text[j] == "org":
            end = j
    if end == d:
        v = next((j for j in range(d + 1, min(d + 12, len(ws))) if text[j] == "visit"), None)
        if v is not None:
            # Address garbled: take everything up to the first clear pause after "visit".
            end = v
            while end + 1 < len(ws) and ws[end + 1]["start"] - ws[end]["end"] < 0.35 and end - v < 6:
                end += 1
    # Then skip ahead to where the reader announces the chapter ("Chapter one...", "Stave one...") and start just before it.
    for k in range(end + 1, len(ws)):
        if ws[k]["start"] > ws[end]["end"] + 45:
            break
        if text[k] in ANNOUNCE:
            if text[k - 1] in ("the", "a") and k - 1 > end and ws[k]["start"] - ws[k - 1]["end"] < 0.3:
                k -= 1  # keep "The" in "The Adventure of ..."
            prev = ws[k - 1]["end"]
            return round(max(prev + (ws[k]["start"] - prev) / 2, ws[k]["start"] - 0.4), 2)
    stop = ws[end]["end"]
    nxt = ws[end + 1]["start"] if end + 1 < len(ws) else stop + 0.6
    # No announcement heard: start in the middle of the pause after the notice, so the cut lands in silence.
    return round(min(stop + (nxt - stop) / 2, stop + 0.8), 2)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--show", action="store_true", help="print what was heard")
    ap.add_argument("ids", nargs="*")
    a = ap.parse_args()
    from vosk import Model, SetLogLevel
    SetLogLevel(-1)
    model = Model(a.model)
    cat = json.loads(CATALOG.read_text())
    for b in cat:
        if a.ids and b["id"] not in a.ids:
            continue
        meta = json.load(urllib.request.urlopen(f"https://archive.org/metadata/{b['ia']}", timeout=60))
        servers = [h for h in dict.fromkeys([meta.get("d1"), meta.get("d2"), meta.get("server")]) if h]
        found = 0
        for c in b["ch"]:
            cached = CACHE / f"{b['ia']}__{c[1]}.json"
            if cached.exists():
                ws = json.loads(cached.read_text())
                t = intro_end(ws)
                del c[3:]
                if t:
                    c.append(t)
                    found += 1
                if a.show:
                    print(f"  {c[0]}: start at {t}s | ... " + " ".join(w["word"] for w in ws if (t or 25) - 3 < w["start"] < (t or 25) + 4) + " ...", flush=True)
                continue
            audio = None
            for h in servers:  # each item is stored on two servers; use whichever answers
                try:
                    audio = pcm(f"https://{h}{meta['dir']}/{c[1]}")
                    break
                except subprocess.CalledProcessError:
                    continue
            if audio is None:
                print(f"  {c[0]}: could not download, left unchanged", flush=True)
                continue
            ws = words(model, audio)
            CACHE.mkdir(parents=True, exist_ok=True)
            cached.write_text(json.dumps(ws))
            t = intro_end(ws)
            del c[3:]
            if t:
                c.append(t)
                found += 1
            if a.show:
                print(f"  {c[0]}: start at {t}s | ... " + " ".join(w["word"] for w in ws if (t or 25) - 3 < w["start"] < (t or 25) + 4) + " ...")
        print(f"{b['title']}: notice found in {found} of {len(b['ch'])} chapters", flush=True)
        CATALOG.write_text("[\n" + ",\n".join(json.dumps(x, ensure_ascii=False, separators=(",", ":")) for x in cat) + "\n]\n")


if __name__ == "__main__":
    main()
