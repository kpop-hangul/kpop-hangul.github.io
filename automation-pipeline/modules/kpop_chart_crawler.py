#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
K-Pop Chart Harvester: Scrapes real-time Melon Top 100 & Spotify Daily Top Charts
Filters against published songs database and returns daily candidate tracks.
"""

import os
import json
import re
import urllib.request
from typing import List, Dict, Any, Optional
from bs4 import BeautifulSoup

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(os.path.dirname(SCRIPT_DIR), "data")
PUBLISHED_FILE = os.path.join(DATA_DIR, "published_songs.json")
CACHE_FILE = os.path.join(DATA_DIR, "chart_cache.json")

os.makedirs(DATA_DIR, exist_ok=True)

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"

# Artist genre heuristic lookup
GENRE_MAP = {
    "aespa": "Dance & Pop",
    "newjeans": "Dance & Pop",
    "illit": "Dance & Pop",
    "ive": "Dance & Pop",
    "rescene": "Dance & Pop",
    "twice": "Dance & Pop",
    "le sserafim": "Dance & Pop",
    "babymonster": "Hip-Hop & Rap",
    "blackpink": "Dance & Pop",
    "bts": "Dance & Pop",
    "stray kids": "Hip-Hop & Rap",
    "ateez": "Hip-Hop & Rap",
    "bigbang": "Hip-Hop & Rap",
    "cortis": "Hip-Hop & Rap",
    "big naughty": "R&B & Soul",
    "zico": "Hip-Hop & Rap",
    "taeyeon": "Ballad & OST",
    "iu": "Ballad & OST",
    "day6": "Rock & Band",
    "qwer": "Rock & Band",
    "akmu": "Indie & Acoustic",
    "10cm": "Indie & Acoustic",
    "paul kim": "Ballad & OST",
    "lim young woong": "Ballad & OST",
    "roy kim": "Ballad & OST",
    "eclipse": "Rock & Band",
    "seventeen": "Dance & Pop",
    "riize": "Dance & Pop",
    "tws": "Dance & Pop",
    "boynextdoor": "Dance & Pop",
    "nct dream": "Dance & Pop",
    "nct 127": "Hip-Hop & Rap",
    "kiss of life": "R&B & Soul",
    "i.o.i": "Dance & Pop"
}


def load_published_songs() -> List[Dict[str, Any]]:
    """Loads history of published songs to prevent duplicate articles."""
    if os.path.exists(PUBLISHED_FILE):
        try:
            with open(PUBLISHED_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []


def save_published_song(song_info: Dict[str, Any]):
    """Records a newly published song to the database."""
    published = load_published_songs()
    # Check if already exists
    sig = f"{song_info.get('artist', '').lower()}:{song_info.get('songTitle', '').lower()}"
    for item in published:
        item_sig = f"{item.get('artist', '').lower()}:{item.get('songTitle', '').lower()}"
        if item_sig == sig:
            return

    published.append(song_info)
    with open(PUBLISHED_FILE, "w", encoding="utf-8") as f:
        json.dump(published, f, ensure_ascii=False, indent=2)


def is_song_published(artist: str, title: str, published_list: List[Dict[str, Any]]) -> bool:
    """Checks if a song has already been covered."""
    def clean(text: str) -> str:
        t = re.sub(r"\s*[\(\[].*?[\)\]]", "", text).lower().strip()
        return re.sub(r"[^\w가-힣]", "", t)

    target_artist = clean(artist)
    target_title = clean(title)

    for item in published_list:
        pub_artist = clean(item.get("artist", ""))
        pub_title = clean(item.get("songTitle", item.get("title", "")))

        if (target_artist in pub_artist or pub_artist in target_artist) and \
           (target_title in pub_title or pub_title in target_title):
            return True
    return False


def infer_genre(artist: str, title: str) -> str:
    """Guesses genre from known artist catalog or keywords."""
    norm_artist = re.sub(r"\(.*?\)", "", artist).lower().strip()
    for known_artist, genre in GENRE_MAP.items():
        if known_artist in norm_artist:
            return genre

    norm_title = title.lower()
    if any(w in norm_title for w in ["ost", "ballad", "part.", "soundtrack", "theme"]):
        return "Ballad & OST"
    if any(w in norm_title for w in ["feat", "rap", "cypher", "hip"]):
        return "Hip-Hop & Rap"
    if any(w in norm_title for w in ["band", "rock"]):
        return "Rock & Band"

    return "Dance & Pop"


def infer_initial_difficulty(artist: str, title: str, genre: str) -> str:
    """Provides initial difficulty tier suggestion before AI verification."""
    if genre == "Hip-Hop & Rap":
        return "Advanced"
    if genre in ["Ballad & OST", "Rock & Band"]:
        return "Intermediate"
    if any(k in artist.lower() for k in ["newjeans", "illit", "twice", "ive", "rescene"]):
        return "Beginner"
    return "Intermediate"


def fetch_melon_top100(limit: int = 50) -> List[Dict[str, Any]]:
    """Scrapes top tracks from Melon chart."""
    req = urllib.request.Request(
        "https://www.melon.com/chart/index.htm",
        headers={"User-Agent": USER_AGENT}
    )
    songs = []
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            soup = BeautifulSoup(resp.read().decode("utf-8"), "html.parser")
            rows = soup.select("table tbody tr")[:limit]
            for i, row in enumerate(rows, 1):
                title_el = row.select_one("div.ellipsis.rank01 a")
                artist_el = row.select_one("div.ellipsis.rank02 a")
                album_el = row.select_one("div.ellipsis.rank03 a")

                if title_el and artist_el:
                    raw_artist = artist_el.text.strip().replace("\xa0", " ")
                    title = title_el.text.strip()
                    album = album_el.text.strip() if album_el else ""

                    # Extract Hangul and English artist names
                    genre = infer_genre(raw_artist, title)
                    diff = infer_initial_difficulty(raw_artist, title, genre)

                    songs.append({
                        "rank": i,
                        "chartSource": "Melon Top 100",
                        "artist": raw_artist,
                        "title": title,
                        "album": album,
                        "genre": genre,
                        "difficulty": diff
                    })
    except Exception as e:
        print(f"⚠️ [MelonCrawler] Failed to fetch Melon chart: {e}")
    return songs


def fetch_spotify_daily(limit: int = 50) -> List[Dict[str, Any]]:
    """Scrapes daily top Spotify tracks for Korea."""
    req = urllib.request.Request(
        "https://kworb.net/spotify/country/kr_daily.html",
        headers={"User-Agent": USER_AGENT}
    )
    songs = []
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            soup = BeautifulSoup(resp.read().decode("utf-8", errors="ignore"), "html.parser")
            rows = soup.select("table.sortable tbody tr")[:limit]
            for i, r in enumerate(rows, 1):
                tds = r.select("td")
                if len(tds) >= 3:
                    entry = tds[2].text.strip()
                    if " - " in entry:
                        parts = entry.split(" - ", 1)
                        artist = parts[0].strip()
                        title = parts[1].strip()
                    else:
                        artist = "K-Pop Artist"
                        title = entry

                    genre = infer_genre(artist, title)
                    diff = infer_initial_difficulty(artist, title, genre)

                    songs.append({
                        "rank": i,
                        "chartSource": "Spotify Daily Top",
                        "artist": artist,
                        "title": title,
                        "album": "",
                        "genre": genre,
                        "difficulty": diff
                    })
    except Exception as e:
        print(f"⚠️ [SpotifyCrawler] Failed to fetch Spotify chart: {e}")
    return songs


def get_daily_candidate_songs(count: int = 3, force_refresh: bool = False) -> List[Dict[str, Any]]:
    """
    Main function to get 3 new songs from top Melon & Spotify charts
    guaranteed to be unpublished yet.
    """
    published = load_published_songs()

    print(f"🔍 [ChartCrawler] Fetching top charts (Published count: {len(published)})...")
    melon_songs = fetch_melon_top100(limit=50)
    spotify_songs = fetch_spotify_daily(limit=50)

    # Combine candidates
    all_candidates = []
    seen = set()

    # Interleave Melon and Spotify so we get strong global & domestic Korean coverage
    max_len = max(len(melon_songs), len(spotify_songs))
    for idx in range(max_len):
        if idx < len(melon_songs):
            m = melon_songs[idx]
            key = f"{m['artist'].lower()}:{m['title'].lower()}"
            if key not in seen:
                seen.add(key)
                all_candidates.append(m)

        if idx < len(spotify_songs):
            s = spotify_songs[idx]
            key = f"{s['artist'].lower()}:{s['title'].lower()}"
            if key not in seen:
                seen.add(key)
                all_candidates.append(s)

    # Filter out already published songs
    unwritten_songs = []
    for cand in all_candidates:
        if not is_song_published(cand["artist"], cand["title"], published):
            unwritten_songs.append(cand)
            if len(unwritten_songs) >= count:
                break

    # Cache candidates
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(unwritten_songs, f, ensure_ascii=False, indent=2)

    return unwritten_songs


if __name__ == "__main__":
    candidates = get_daily_candidate_songs(count=3)
    print(f"\n🎵 Selected {len(candidates)} songs for today:")
    for c in candidates:
        print(f" - #{c['rank']} [{c['chartSource']}] {c['artist']} - {c['title']} ({c['genre']}, {c['difficulty']})")
