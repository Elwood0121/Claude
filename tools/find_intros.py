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
LISTEN = 60  # seconds of audio to scan


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
    """Return the time to start playback, or 0 if no notice was heard."""
    text = [w["word"] for w in ws]
    # The notice ends with "...please visit librivox dot org". The recognizer may mishear "librivox", so key on "org"
    # (or "visit" + up to 4 words) and require the notice's earlier words to appear before it.
    end = None
    for i, w in enumerate(text):
        if ws[i]["start"] > 50:
            break
        if w == "org" and any(t in ("domain", "recording", "recordings", "volunteer", "visit") for t in text[max(0, i - 30):i]):
            end = i
            break
    if end is None:
        for i, w in enumerate(text):
            if w == "visit" and ws[i]["start"] < 50:
                end = min(i + 4, len(ws) - 1)
                break
    if end is None:
        return 0
    # Some readers spell the address out again ("that's L-I-B-R-I-V-O-X dot org"): use the last "org" close by.
    for j in range(end + 1, len(ws)):
        if ws[j]["start"] > ws[end]["end"] + 12:
            break
        if text[j] == "org":
            end = j
    # Also drop a "Read by ..." / "Recorded by ..." credit that follows straight on, up to its first real pause.
    if end + 1 < len(ws) and text[end + 1] in ("read", "recorded", "recording", "reading") and ws[end + 1]["start"] - ws[end]["end"] < 2.5:
        j = end + 1
        while j + 1 < len(ws) and ws[j + 1]["start"] - ws[j]["end"] < 0.45 and ws[j + 1]["start"] < ws[end + 1]["start"] + 10:
            j += 1
        if ws[j]["end"] < ws[end + 1]["start"] + 10:
            end = j
    stop = ws[end]["end"]
    nxt = ws[end + 1]["start"] if end + 1 < len(ws) else stop + 0.6
    # Start in the middle of the pause after "org", so the cut lands in silence.
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
        base = f"https://{meta['server']}{meta['dir']}/"
        found = 0
        for c in b["ch"]:
            ws = words(model, pcm(base + c[1]))
            t = intro_end(ws)
            del c[3:]
            if t:
                c.append(t)
                found += 1
            if a.show:
                print(f"  {c[0]}: start at {t}s | " + " ".join(w["word"] for w in ws if w["start"] < (t or 25) + 4))
        print(f"{b['title']}: notice found in {found} of {len(b['ch'])} chapters", flush=True)
        CATALOG.write_text("[\n" + ",\n".join(json.dumps(x, ensure_ascii=False, separators=(",", ":")) for x in cat) + "\n]\n")


if __name__ == "__main__":
    main()
