#!/usr/bin/env python3
"""
Build or refresh a playlist M3U from its companion YAML.

Usage:
    python scripts/create_playlist.py <path/to/companion.yaml>

Reads the companion YAML, cross-references data/library_index.json, writes
the M3U alongside the YAML, and prints a status report.

Track list in the companion YAML must use the `tracks` key:

  tracks:
    - artist: "KATSEYE"
      title:  "PINKY UP"
      source: "library"       # library | user_request | recommendation
      status: "in_library"    # in_library | pending | acquired | dismissed
"""

import json
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit("pyyaml required — pip install pyyaml")


ROOT = Path(__file__).parent.parent
LIBRARY_FILE = ROOT / "data" / "library_index.json"


def build_index(library: dict) -> dict:
    """Return {(artist_lower, title_lower): {artist, title, path, duration_s}}."""
    idx = {}
    for artist_entry in library["artists"]:
        artist = artist_entry["name"]
        for album in artist_entry["albums"]:
            for track in album["tracks"]:
                key = (artist.lower(), track["title"].lower())
                if key not in idx:  # keep first match (album version beats later remixes)
                    idx[key] = {
                        "artist": artist,
                        "title": track["title"],
                        "path": track["path"],
                        "duration_s": track.get("duration_s", -1),
                    }
    return idx


def lookup(idx: dict, artist: str, title: str) -> dict | None:
    """Exact match first, then loose: title matches and artist names overlap."""
    exact = (artist.lower(), title.lower())
    if exact in idx:
        return idx[exact]
    title_l = title.lower()
    artist_l = artist.lower()
    for (a, t), v in idx.items():
        if t == title_l and (artist_l in a or a in artist_l):
            return v
    return None


def main():
    if len(sys.argv) < 2:
        sys.exit("Usage: create_playlist.py <companion.yaml>")

    companion_path = Path(sys.argv[1])
    if not companion_path.exists():
        sys.exit(f"File not found: {companion_path}")

    with open(companion_path) as f:
        companion = yaml.safe_load(f)

    with open(LIBRARY_FILE) as f:
        library = json.load(f)

    music_root = library["music_root"]
    idx = build_index(library)

    tracks = companion.get("tracks", [])
    if not tracks:
        sys.exit("No 'tracks' list found in companion YAML.")

    in_library = []
    pending = []

    for t in tracks:
        if t.get("status") == "dismissed":
            continue
        result = lookup(idx, t["artist"], t["title"])
        if result:
            in_library.append(result)
        else:
            pending.append(t)

    # Write M3U
    m3u_path = companion_path.with_suffix(".m3u")
    lines = ["#EXTM3U"]
    for t in in_library:
        lines.append(f"#EXTINF:{t['duration_s']},{t['artist']} - {t['title']}")
        lines.append(f"{music_root}/{t['path']}")
    m3u_path.write_text("\n".join(lines) + "\n")

    # Summary
    active = [t for t in tracks if t.get("status") != "dismissed"]
    recs = sum(1 for t in active if t.get("source") == "recommendation")
    rec_pct = round(recs / len(active) * 100) if active else 0

    print(f"✓  {m3u_path.name}  —  {len(in_library)} tracks in M3U")
    print(f"   {len(pending)} pending (not yet in library)")
    print(f"   recommendations: {recs}/{len(active)} ({rec_pct}% — target ≥25%)")

    if pending:
        print("\nPending:")
        for t in pending:
            print(f"  [{t.get('source', '?')}] {t.get('artist')} — {t.get('title')}")


if __name__ == "__main__":
    main()
