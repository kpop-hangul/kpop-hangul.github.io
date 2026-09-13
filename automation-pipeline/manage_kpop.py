#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
K-Pop Hangul Blog Management CLI
Manage daily chart crawlers, pipeline execution, published songs, and site statistics.
"""

import os
import sys
import json
import argparse
from datetime import datetime

PIPELINE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PIPELINE_DIR)

from modules.kpop_chart_crawler import (
    load_published_songs,
    get_daily_candidate_songs,
    fetch_melon_top100,
    fetch_spotify_daily,
)

def print_banner():
    print("=" * 60)
    print("🎵 K-Pop Hangul Blog Management CLI")
    print("=" * 60)

def cmd_status():
    print_banner()
    published = load_published_songs()
    print(f"📊 Total Published Songs: {len(published)}")

    diff_counts = {}
    genre_counts = {}
    for p in published:
        d = p.get("difficulty", "Unknown")
        g = p.get("genre", "Unknown")
        diff_counts[d] = diff_counts.get(d, 0) + 1
        genre_counts[g] = genre_counts.get(g, 0) + 1

    print("\n📚 Breakdown by Difficulty Level:")
    for d, c in sorted(diff_counts.items()):
        print(f"  • {d}: {c} song(s)")

    print("\n🎸 Breakdown by Music Genre:")
    for g, c in sorted(genre_counts.items()):
        print(f"  • {g}: {c} song(s)")

    print("\n📝 Recently Published Tracks:")
    for p in published[-5:]:
        print(f"  - [{p.get('difficulty')}] {p.get('artist')} - {p.get('songTitle', p.get('title'))} ({p.get('chartSource')})")

    # Check systemd timer status
    print("\n⏰ Systemd Automation Service:")
    res = os.system("systemctl --user is-active --quiet auto-blog-kpop-pipeline.timer")
    if res == 0:
        print("  🟢 Timer is ACTIVE (auto-blog-kpop-pipeline.timer)")
    else:
        print("  ⚪ Timer status check: Run 'systemctl --user status auto-blog-kpop-pipeline.timer'")

def cmd_charts():
    print_banner()
    print("🍈 Fetching Melon Top 10:")
    melon = fetch_melon_top100(limit=10)
    for s in melon:
        print(f"  #{s['rank']:02d} | {s['artist']} - {s['title']} ({s['genre']})")

    print("\n🎧 Fetching Spotify Korea Daily Top 10:")
    spotify = fetch_spotify_daily(limit=10)
    for s in spotify:
        print(f"  #{s['rank']:02d} | {s['artist']} - {s['title']} ({s['genre']})")

def cmd_candidates():
    print_banner()
    print("🔍 Fetching next 3 candidate songs for automated publishing:")
    candidates = get_daily_candidate_songs(count=3)
    for idx, c in enumerate(candidates, 1):
        print(f"  {idx}. [{c['difficulty']}] {c['artist']} - {c['title']}")
        print(f"     Rank: #{c['rank']} on {c['chartSource']} | Genre: {c['genre']}")

def cmd_run(count: int = 3):
    print_banner()
    print(f"🚀 Launching Daily K-Pop Pipeline for {count} songs...")
    import subprocess
    cmd = [
        os.path.join(PIPELINE_DIR, "venv", "bin", "python3"),
        os.path.join(PIPELINE_DIR, "daily_kpop_pipeline.py"),
        "--count", str(count)
    ]
    subprocess.run(cmd)

def cmd_images():
    print_banner()
    print("🎨 Scanning and generating missing thumbnails & illustrations for all posts...")
    from pathlib import Path
    import yaml
    from modules.thumbnail_generator import generate_thumbnail_for_post
    from modules.article_image_generator import generate_and_integrate_article_images

    blog_dir = Path(PIPELINE_DIR).parent / "blog-frontend" / "src" / "content" / "blog"
    md_files = sorted(blog_dir.glob("*.md"))
    print(f"Total articles found: {len(md_files)}")

    updated = 0
    for mf in md_files:
        slug = mf.stem
        text = mf.read_text(encoding="utf-8")
        parts = text.split("---", 2)
        if len(parts) < 3:
            continue
        fm_raw, body = parts[1], parts[2]
        try:
            fm = yaml.safe_load(fm_raw) or {}
        except Exception:
            continue

        post_data = {
            "slug": slug,
            "title": fm.get("title", ""),
            "artist": fm.get("artist", "K-Pop Artist"),
            "songTitle": fm.get("songTitle", ""),
            "hangulTitle": fm.get("hangulTitle", ""),
            "difficulty": fm.get("difficulty", "Beginner"),
            "genre": fm.get("genre", "Dance & Pop"),
            "chartRank": fm.get("chartRank"),
            "chartSource": fm.get("chartSource", "Melon Top 100"),
        }
        thumb_url = generate_thumbnail_for_post(post_data)
        fm["heroImage"] = thumb_url

        article_obj = {
            "songTitle": fm.get("songTitle", ""),
            "artist": fm.get("artist", ""),
            "difficulty": fm.get("difficulty", "Beginner"),
            "genre": fm.get("genre", "Dance & Pop"),
            "markdown_content": body.strip()
        }
        updated_body, imgs = generate_and_integrate_article_images(article_obj, slug)

        new_fm_str = yaml.safe_dump(fm, allow_unicode=True, sort_keys=False)
        new_full_content = f"---\n{new_fm_str}---\n\n{updated_body}\n"
        mf.write_text(new_full_content, encoding="utf-8")
        updated += 1

    print(f"✨ Successfully refreshed thumbnails and illustrations for {updated} posts!")

def main():
    parser = argparse.ArgumentParser(description="K-Pop Hangul Blog Management CLI")
    parser.add_argument("action", choices=["status", "charts", "candidates", "run", "images"], nargs="?", default="status",
                        help="Action to perform (status, charts, candidates, run, images)")
    parser.add_argument("--count", type=int, default=3, help="Number of songs for pipeline run")

    args = parser.parse_args()

    if args.action == "status":
        cmd_status()
    elif args.action == "charts":
        cmd_charts()
    elif args.action == "candidates":
        cmd_candidates()
    elif args.action == "run":
        cmd_run(count=args.count)
    elif args.action == "images":
        cmd_images()

if __name__ == "__main__":
    main()
