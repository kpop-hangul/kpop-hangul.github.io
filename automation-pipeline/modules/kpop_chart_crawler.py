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
    "i.o.i": "Dance & Pop",
    "hanroro": "Indie & Acoustic",
    "nerd connection": "Rock & Band",
    "kiiikiii": "Dance & Pop",
    "hearts2hearts": "Dance & Pop",
    "redoor": "Indie & Acoustic"
}

KNOWN_KPOP_ARTISTS = [
    "bts", "blackpink", "newjeans", "aespa", "ive", "le sserafim", "twice",
    "stray kids", "seventeen", "ateez", "txt", "enhypen", "riize", "tws",
    "boynextdoor", "zerobaseone", "babymonster", "itzy", "nmixx", "red velvet",
    "nct", "nct dream", "nct 127", "nct wish", "wayv", "exo", "shinee",
    "monsta x", "the boyz", "stayc", "kiss of life", "illit", "rescene",
    "day6", "qwer", "plave", "lucy", "jannabi", "the rose", "ftisland", "cnblue",
    "akmu", "bol4", "10cm", "melomance", "nerd connection", "hanroro",
    "iu", "taeyeon", "paul kim", "roy kim", "lim young woong", "lee mujin",
    "lee young ji", "bibi", "crush", "heize", "dean", "zion.t", "sam kim",
    "bigbang", "g-dragon", "taeyang", "daesung", "zico", "block b", "big naughty",
    "cortis", "changmo", "beenzino", "jay park", "giriboy", "ash island",
    "jungkook", "jung kook", "jimin", "v", "rm", "jin", "suga", "j-hope",
    "jennie", "rosé", "rose", "lisa", "jisoo", "nayeon", "jihyo", "miyeon",
    "yuqi", "soyeon", "(g)i-dle", "gidle", "i.o.i", "iz*one", "kep1er",
    "triples", "artms", "loossemble", "chuu", "sunmi", "chungha", "hyuna",
    "kiiikiii", "redoor", "hearts2hearts", "woodz", "baekhyun", "d.o."
]

EXCLUDED_NON_KPOP = [
    "post malone", "taylor swift", "bruno mars", "lady gaga", "benson boone",
    "sabrina carpenter", "billie eilish", "ariana grande", "justin bieber",
    "ed sheeran", "coldplay", "the weeknd", "charlie puth", "dua lipa",
    "olivia rodrigo", "kendrick lamar", "eminem", "imagine dragons",
    "maroon 5", "sam smith", "troye sivan", "keshi", "lauv", "d4vd",
    "conan gray", "chappell roan", "travis scott", "drake", "sza",
    "tate mcrae", "gracie abrams", "teddy swims", "shaboozey", "tom odell",
    "beyonce", "rihanna", "harry styles", "miley cyrus", "kanye west"
]


def is_kpop_candidate(artist: str, title: str) -> bool:
    """Verifies that the candidate is indeed a K-Pop / Korean song suitable for learning Hangul."""
    art_lower = artist.lower()
    tit_lower = title.lower()

    # 1. Reject if explicitly in excluded non-Korean list (unless featuring a Korean artist or containing Hangul)
    for excluded in EXCLUDED_NON_KPOP:
        if excluded in art_lower:
            if not re.search(r"[\uac00-\ud7a3]", artist + " " + title):
                return False

    # 2. Accept if contains Hangul characters in artist or title
    if re.search(r"[\uac00-\ud7a3]", artist) or re.search(r"[\uac00-\ud7a3]", title):
        return True

    # 3. Accept if artist is in known K-Pop artists or genre map
    for known in GENRE_MAP:
        if known in art_lower:
            return True

    for known in KNOWN_KPOP_ARTISTS:
        if known in art_lower:
            return True

    # 4. Fallback: If title or artist contains typical K-Pop terms (OST, Part, etc.)
    if any(k in tit_lower for k in ["ost", "drama", "korean", "hangul"]):
        return True

    return False



def load_published_songs():
    if not os.path.exists(PUBLISHED_FILE):
        return []
    with open(PUBLISHED_FILE, encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, list):
        raise ValueError("Invalid published song history")
    return data


def save_published_song(song_info):
    from modules.atomic_storage import file_lock, atomic_json
    with file_lock(PUBLISHED_FILE):
        published = load_published_songs()
        sig = f"{song_info.get('artist', '').lower()}:{song_info.get('songTitle', '').lower()}"
        if any(f"{x.get('artist', '').lower()}:{x.get('songTitle', '').lower()}" == sig for x in published):
            return
        published.append(song_info)
        atomic_json(PUBLISHED_FILE, published)


def is_song_published(artist: str, title: str, published_list: List[Dict[str, Any]]) -> bool:
    """
    Checks if a song has already been covered.
    Uses normalized signature and word-token matching to prevent false positives
    for artists with short names (e.g. 'V', 'RM', 'Jin').
    """
    def clean(text: str) -> str:
        t = re.sub(r"\s*[\(\[].*?[\)\]]", "", text).lower().strip()
        return re.sub(r"[^\w가-힣]", "", t)

    target_artist = clean(artist)
    target_title = clean(title)

    if not target_artist or not target_title:
        return False

    target_artist_words = set(re.findall(r"[\w가-힣]+", target_artist))
    target_title_words = set(re.findall(r"[\w가-힣]+", target_title))

    for item in published_list:
        pub_artist = clean(item.get("artist", ""))
        pub_title = clean(item.get("songTitle", item.get("title", "")))

        # 1. Exact normalized match
        if target_artist == pub_artist and target_title == pub_title:
            return True

        # 2. Token set matching: Both artist tokens and title tokens must have significant overlap
        pub_artist_words = set(re.findall(r"[\w가-힣]+", pub_artist))
        pub_title_words = set(re.findall(r"[\w가-힣]+", pub_title))

        artist_match = (target_artist == pub_artist) or bool(target_artist_words and pub_artist_words and target_artist_words == pub_artist_words)
        title_match = (target_title == pub_title) or bool(target_title_words and pub_title_words and target_title_words == pub_title_words)

        if artist_match and title_match:
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


import random
import time

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1"
]


def fetch_url_with_retries(url: str, retries: int = 3, initial_delay: float = 1.0, timeout: int = 15) -> Optional[str]:
    """Fetches URL contents with exponential backoff and rotating user-agents."""
    for attempt in range(1, retries + 1):
        user_agent = random.choice(USER_AGENTS)
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": user_agent,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
            }
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read().decode("utf-8", errors="ignore")
        except Exception as e:
            if attempt < retries:
                delay = initial_delay * (2 ** (attempt - 1)) + random.uniform(0.1, 0.5)
                print(f"⚠️ [ChartCrawler] Attempt {attempt}/{retries} failed for {url}: {e}. Retrying in {delay:.2f}s...")
                time.sleep(delay)
            else:
                print(f"❌ [ChartCrawler] All {retries} attempts failed for {url}: {e}")
    return None


def fetch_melon_top100(limit: int = 50) -> List[Dict[str, Any]]:
    """Scrapes top tracks from Melon chart with retry protection."""
    html = fetch_url_with_retries("https://www.melon.com/chart/index.htm", retries=3, timeout=25)
    songs = []
    if not html:
        return songs

    try:
        soup = BeautifulSoup(html, "html.parser")
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
        print(f"⚠️ [MelonCrawler] Failed to parse Melon chart: {e}")
    return songs


def fetch_spotify_daily(limit: int = 50) -> List[Dict[str, Any]]:
    """Scrapes daily top Spotify tracks for Korea with retry protection."""
    html = fetch_url_with_retries("https://kworb.net/spotify/country/kr_daily.html", retries=3, timeout=25)
    songs = []
    if not html:
        return songs

    try:
        soup = BeautifulSoup(html, "html.parser")
        rows = soup.select("table.sortable tbody tr")[:limit]
        for i, r in enumerate(rows, 1):
            tds = r.select("td")
            if len(tds) >= 3:
                entry = tds[2].text.strip()
                match = re.search(r"\s+[-–—]\s+", entry)
                if match:
                    parts = re.split(r"\s+[-–—]\s+", entry, maxsplit=1)
                    artist = parts[0].strip()
                    title = parts[1].strip() if len(parts) > 1 else entry
                elif " - " in entry:
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
        print(f"⚠️ [SpotifyCrawler] Failed to parse Spotify chart: {e}")
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

    # Combine candidates with cross-chart deduplication
    def norm_sig(art: str, tit: str) -> str:
        ca = re.sub(r"[\(\[].*?[\)\]]", "", art).lower()
        ca = re.sub(r"[^\w가-힣]", "", ca).strip()
        ct = re.sub(r"[\(\[].*?[\)\]]", "", tit).lower()
        ct = re.sub(r"[^\w가-힣]", "", ct).strip()
        return f"{ca}:{ct}"

    all_candidates = []
    seen = set()

    # Interleave Melon and Spotify so we get strong global & domestic Korean coverage
    max_len = max(len(melon_songs), len(spotify_songs))
    for idx in range(max_len):
        if idx < len(melon_songs):
            m = melon_songs[idx]
            sig = norm_sig(m['artist'], m['title'])
            if sig not in seen:
                seen.add(sig)
                all_candidates.append(m)

        if idx < len(spotify_songs):
            s = spotify_songs[idx]
            sig = norm_sig(s['artist'], s['title'])
            if sig not in seen:
                seen.add(sig)
                all_candidates.append(s)

    # Filter out already published songs and non-K-Pop tracks
    unwritten_songs = []
    for cand in all_candidates:
        if not is_kpop_candidate(cand["artist"], cand["title"]):
            continue
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
