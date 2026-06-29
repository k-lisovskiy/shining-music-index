#!/usr/bin/env python3
"""
Scan the music library and write data/library_index.json.

Usage:
    python scripts/index_library.py [--music-root PATH]

Defaults to /Volumes/COMICS/Music. Re-run whenever new music is added.
"""

import argparse
import json
import os
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


MUSIC_ROOT_DEFAULT = "/Volumes/COMICS/Music"
OUTPUT_FILE = Path(__file__).parent.parent / "data" / "library_index.json"


def extract_flac_metadata(path: Path) -> dict:
    try:
        from mutagen.flac import FLAC
        audio = FLAC(str(path))
        tags = audio.tags or {}

        def first(key):
            val = tags.get(key.upper()) or tags.get(key.lower())
            return val[0] if val else None

        duration_s = int(audio.info.length) if audio.info else None
        track_str = first("tracknumber") or ""
        try:
            track_num = int(track_str.split("/")[0])
        except (ValueError, AttributeError):
            track_num = None

        return {
            "title": first("title"),
            "artist": first("artist"),
            "album": first("album"),
            "album_artist": first("albumartist"),
            "year": first("date"),
            "genre": first("genre"),
            "track_number": track_num,
            "duration_s": duration_s,
        }
    except Exception:
        return {}


def parse_filename(filename: str) -> dict:
    """Fallback: parse 'NN Artist Name - Track Title.flac' convention."""
    stem = Path(filename).stem
    m = re.match(r"^\d+\s+(.+?)\s+-\s+(.+)$", stem)
    if m:
        return {"artist": m.group(1).strip(), "title": m.group(2).strip()}
    return {"title": stem}


def build_index(music_root: str) -> dict:
    root = Path(music_root)
    if not root.exists():
        print(f"ERROR: Music root not found: {music_root}", file=sys.stderr)
        sys.exit(1)

    # artist_name → album_name → list of tracks
    tree: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
    # album metadata keyed by (artist, album)
    album_meta: dict[tuple, dict] = {}

    flac_files = sorted(root.rglob("*.flac"))
    flac_files = [f for f in flac_files if not f.name.startswith("._")]

    for flac_path in flac_files:
        rel = flac_path.relative_to(root)
        parts = rel.parts  # e.g. ('Taylor Swift', 'folklore', '01 Taylor Swift - the 1.flac')

        if len(parts) < 3:
            continue  # unexpected structure — skip

        dir_artist = parts[0]
        dir_album = parts[1]

        meta = extract_flac_metadata(flac_path)
        fallback = parse_filename(parts[-1])

        artist = meta.get("album_artist") or meta.get("artist") or dir_artist
        album = meta.get("album") or dir_album
        title = meta.get("title") or fallback.get("title") or parts[-1]

        track = {
            "number": meta.get("track_number"),
            "title": title,
            "duration_s": meta.get("duration_s"),
            "path": str(rel),
        }

        tree[artist][album].append(track)

        key = (artist, album)
        if key not in album_meta:
            album_meta[key] = {
                "year": meta.get("year"),
                "genre": meta.get("genre"),
            }

    artists_out = []
    for artist_name in sorted(tree):
        albums_out = []
        for album_name in sorted(tree[artist_name]):
            tracks = sorted(
                tree[artist_name][album_name],
                key=lambda t: (t["number"] or 999, t["title"]),
            )
            meta = album_meta.get((artist_name, album_name), {})
            albums_out.append({
                "name": album_name,
                "year": meta.get("year"),
                "genre": meta.get("genre"),
                "tracks": tracks,
            })
        artists_out.append({"name": artist_name, "albums": albums_out})

    total_albums = sum(len(a["albums"]) for a in artists_out)
    total_tracks = sum(
        len(al["tracks"]) for a in artists_out for al in a["albums"]
    )

    return {
        "generated": datetime.now(timezone.utc).isoformat(),
        "music_root": str(root),
        "stats": {
            "artists": len(artists_out),
            "albums": total_albums,
            "tracks": total_tracks,
        },
        "artists": artists_out,
    }


def main():
    parser = argparse.ArgumentParser(description="Index the local music library.")
    parser.add_argument(
        "--music-root",
        default=MUSIC_ROOT_DEFAULT,
        help=f"Path to music folder (default: {MUSIC_ROOT_DEFAULT})",
    )
    args = parser.parse_args()

    print(f"Scanning {args.music_root} ...")
    index = build_index(args.music_root)

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(index, f, indent=2, ensure_ascii=False)

    s = index["stats"]
    print(
        f"Indexed {s['artists']} artists, {s['albums']} albums, "
        f"{s['tracks']} tracks → {OUTPUT_FILE}"
    )


if __name__ == "__main__":
    main()
