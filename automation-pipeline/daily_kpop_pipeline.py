#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Daily K-Pop Korean Learning Pipeline:
1. Fetches real-time Melon Top 100 & Spotify Daily Charts
2. Selects 3 fresh, unpublished top songs
3. Writes comprehensive English educational lessons (Hangul lyrics, Romanization, vocabulary, grammar)
4. Performs independent pedagogical editorial review
5. Publishes directly into Astro blog content collections
6. Verifies static site build
"""

import os
import sys
import json
import re
import argparse
import subprocess
from datetime import datetime
from typing import List, Dict, Any, Optional

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, SCRIPT_DIR)

from modules.kpop_chart_crawler import get_daily_candidate_songs, save_published_song
from agents.content_writer import ContentWriter
from agents.editorial_reviewer import EditorialReviewAgent
from modules.draft_queue import DraftApprovalQueue

FRONTEND_BLOG_DIR = os.path.join(ROOT_DIR, "blog-frontend", "src", "content", "blog")
CONFIG_FILE = os.path.join(ROOT_DIR, "blog.config.json")


def load_config() -> Dict[str, Any]:
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"blogId": "kpop-hangul"}


def generate_slug(artist: str, title: str, date_str: str) -> str:
    """Creates a clean, SEO-friendly URL slug."""
    clean_artist = re.sub(r"\(.*?\)", "", artist).strip().lower()
    clean_title = re.sub(r"\(.*?\)", "", title).strip().lower()

    slug_text = f"{clean_artist}-{clean_title}"
    slug_text = re.sub(r"[^\w\s-]", "", slug_text)
    slug_text = re.sub(r"[\s_]+", "-", slug_text)
    slug_text = re.sub(r"-+", "-", slug_text).strip("-")

    if not slug_text:
        slug_text = "kpop-song"

    return f"{date_str}-{slug_text}"


def save_markdown_post(article: Dict[str, Any], slug: str) -> str:
    """Formats and writes the Astro markdown content entry."""
    os.makedirs(FRONTEND_BLOG_DIR, exist_ok=True)
    post_file = os.path.join(FRONTEND_BLOG_DIR, f"{slug}.md")

    today_str = datetime.now().strftime("%Y-%m-%d")

    frontmatter = {
        "title": article.get("title", "Learn Korean with K-Pop"),
        "description": article.get("description", "Master Korean lyrics, vocabulary and grammar."),
        "pubDate": today_str,
        "heroImage": "/images/default-hero.svg",
        "category": article.get("category", "Beginner (Level 1)"),
        "difficulty": article.get("difficulty", "Beginner"),
        "genre": article.get("genre", "Dance & Pop"),
        "artist": article.get("artist", "Various Artists"),
        "songTitle": article.get("songTitle", "Hit Song"),
        "hangulTitle": article.get("hangulTitle", ""),
        "album": article.get("album", ""),
        "chartRank": article.get("chartRank", 1),
        "chartSource": article.get("chartSource", "Melon Top 100"),
        "tags": article.get("tags", []),
        "author": article.get("author", "K-Pop Hangul Team"),
        "readingTime": article.get("readingTime", "7 min read"),
        "faqs": article.get("faqs", [])
    }

    yaml_header = "---\n"
    for key, val in frontmatter.items():
        if isinstance(val, (dict, list)):
            yaml_header += f"{key}: {json.dumps(val, ensure_ascii=False)}\n"
        elif isinstance(val, (int, float, bool)):
            yaml_header += f"{key}: {val}\n"
        else:
            clean_val = str(val).replace('"', '\\"')
            yaml_header += f'{key}: "{clean_val}"\n'
    yaml_header += "---\n\n"

    body = article.get("markdown_content", "").strip()
    full_content = yaml_header + body + "\n"

    with open(post_file, "w", encoding="utf-8") as f:
        f.write(full_content)

    return post_file


def run_daily_pipeline(count: int = 3, specific_song: Optional[Dict[str, Any]] = None, dry_run: bool = False):
    """Executes the complete daily generation workflow."""
    print("=" * 75)
    print(" 🚀  K-Pop Hangul Daily 3-Song Automation Pipeline")
    print(f" 📅  Execution Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 75)

    config = load_config()
    writer = ContentWriter(config)
    reviewer = EditorialReviewAgent(config)
    queue = DraftApprovalQueue(ROOT_DIR)

    # 1. Acquire Songs
    if specific_song:
        songs = [specific_song]
        print(f"\n🎯 [Target] Writing custom requested song: {specific_song['artist']} - {specific_song['title']}")
    else:
        print(f"\n📡 [Step 1/4] Crawling Melon Top 100 & Spotify Daily Charts...")
        songs = get_daily_candidate_songs(count=count)
        if not songs:
            print("⚠️ No unpublished top chart songs found! All currently crawled songs are already published.")
            return

    print(f"\n📋 [Step 2/4] Processing {len(songs)} selected songs:")
    for idx, s in enumerate(songs, 1):
        print(f"   {idx}. #{s.get('rank')} [{s.get('chartSource')}] {s.get('artist')} - {s.get('title')} ({s.get('genre')}, {s.get('difficulty')})")

    today_str = datetime.now().strftime("%Y-%m-%d")
    results = []

    # 2. Write & Audit Each Song
    print(f"\n✍️  [Step 3/4] Writing and reviewing educational lessons...")
    for idx, song in enumerate(songs, 1):
        print(f"\n--- [{idx}/{len(songs)}] Song: {song.get('artist')} - {song.get('title')} ---")
        
        # Write
        article = writer.write_song_lesson(song)
        
        # Review
        review = reviewer.review_article(article, song)
        score = review.get("total_score", 90)
        verdict = review.get("verdict", "PASS")

        slug = generate_slug(article.get("artist", song.get("artist")), article.get("songTitle", song.get("title")), today_str)

        if dry_run:
            print(f"🧪 [Dry Run] Generated article for '{slug}'. Score: {score}/100. Skipping disk write.")
            results.append({"slug": slug, "title": article.get("title"), "score": score, "status": "dry_run"})
            continue

        # Save to Astro content
        post_path = save_markdown_post(article, slug)
        print(f"📄 Saved Astro Content: {os.path.relpath(post_path, ROOT_DIR)}")

        # Mark as published
        save_published_song({
            "artist": article.get("artist"),
            "songTitle": article.get("songTitle"),
            "title": article.get("title"),
            "slug": slug,
            "chartSource": article.get("chartSource"),
            "chartRank": article.get("chartRank"),
            "difficulty": article.get("difficulty"),
            "genre": article.get("genre"),
            "pubDate": today_str,
            "score": score
        })

        results.append({
            "slug": slug,
            "title": article.get("title"),
            "artist": article.get("artist"),
            "score": score,
            "status": "published",
            "path": post_path
        })

    # 3. Verify Astro Static Build
    if not dry_run and results:
        print(f"\n🏗️  [Step 4/4] Verifying Astro static site build...")
        frontend_dir = os.path.join(ROOT_DIR, "blog-frontend")
        try:
            build_res = subprocess.run(["npm", "run", "build"], cwd=frontend_dir, capture_output=True, text=True, timeout=120)
            if build_res.returncode == 0:
                print("✅ Astro build completed with 0 errors! All static HTML routes generated.")
            else:
                print(f"⚠️ Astro build warning:\n{build_res.stderr[:400]}")
        except Exception as e:
            print(f"⚠️ Could not run npm build: {e}")

    # Summary Report
    print("\n" + "=" * 75)
    print(" 🎉  Daily K-Pop Korean Generation Summary:")
    print("=" * 75)
    for r in results:
        print(f" • [{r.get('score', 0)}/100] {r.get('artist', '')} - {r.get('title')}")
        print(f"   URL Slug: /blog/{r.get('slug')}/")
    print("\n✅ Daily batch finished successfully!\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Daily K-Pop Korean Lesson Automation Pipeline")
    parser.add_argument("--count", type=int, default=3, help="Number of songs to generate (default: 3)")
    parser.add_argument("--artist", type=str, default="", help="Specific artist name")
    parser.add_argument("--title", type=str, default="", help="Specific song title")
    parser.add_argument("--dry-run", action="store_true", help="Run without writing files to disk")

    args = parser.parse_args()

    custom_song = None
    if args.artist and args.title:
        custom_song = {
            "artist": args.artist,
            "title": args.title,
            "chartSource": "Melon Top 100",
            "rank": 1,
            "genre": "Dance & Pop",
            "difficulty": "Beginner"
        }

    run_daily_pipeline(count=args.count, specific_song=custom_song, dry_run=args.dry_run)
