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
    """Prepare GPT image updates for existing posts; human approval publishes them."""
    print_banner()
    from pathlib import Path
    import yaml
    from daily_kpop_pipeline import load_config
    from agents.editorial_reviewer import EditorialReviewAgent
    from modules.gpt_images import prepare_article_images
    from modules.draft_queue import DraftApprovalQueue

    config = load_config()
    queue = DraftApprovalQueue()
    reviewer = EditorialReviewAgent(config)
    blog_dir = Path(PIPELINE_DIR).parent / "blog-frontend/src/content/blog"
    count = 0
    for path in sorted(blog_dir.glob("*.md")):
        parts = path.read_text(encoding="utf-8").split("---", 2)
        if len(parts) != 3:
            continue
        metadata = yaml.safe_load(parts[1]) or {}
        article = prepare_article_images({**metadata, "slug": path.stem,
            "existing_slug": path.stem, "markdown_content": parts[2].strip()}, config)
        topic = {"title": article["title"], "existing_slug": path.stem}
        review = reviewer.review_article(article, topic)
        draft_id = queue.add_draft(article, review, topic, existing_slug=path.stem)
        print(f"Queued image update: {draft_id} ({path.stem})")
        count += 1
    print(f"Prepared {count} image updates. Review and approve each draft to publish.")


def cmd_queue():
    print_banner()
    from modules.draft_queue import DraftApprovalQueue
    queue = DraftApprovalQueue(PIPELINE_DIR)
    pending = queue.list_pending()
    print(f"📋 Pending Draft Review Queue: {len(pending)} item(s)")
    if not pending:
        print("  ✅ No drafts waiting for review.")
        return
    for idx, d in enumerate(pending, 1):
        score = d.get("review", {}).get("total_score", "N/A")
        verdict = d.get("review", {}).get("verdict", "")
        print(f"  {idx}. [{score}pt / {verdict}] ID: {d['draft_id']}")
        print(f"     Title: {d.get('title')}")
        print(f"     Created: {d.get('created_at')}")
    print("\n💡 To approve: python3 manage_kpop.py approve <draft_id>")
    print("💡 To reject:  python3 manage_kpop.py reject <draft_id>")

def cmd_approve(draft_id: str):
    print_banner()
    if not draft_id:
        print("⚠️ Please specify a draft ID to approve: python3 manage_kpop.py approve <draft_id>")
        return
    from daily_kpop_pipeline import load_config, publish_queued_draft
    config = load_config()
    print(f"🚀 Approving & Publishing K-Pop draft: {draft_id}...")
    success, res = publish_queued_draft(config, draft_id, human_approved=True)
    if success:
        print(f"🎉 Successfully published!\nURL: {res}")
    else:
        print(f"❌ Failed to publish: {res}")

def cmd_reject(draft_id: str):
    print_banner()
    if not draft_id:
        print("⚠️ Please specify a draft ID to reject: python3 manage_kpop.py reject <draft_id>")
        return
    from modules.draft_queue import DraftApprovalQueue
    queue = DraftApprovalQueue(PIPELINE_DIR)
    ok = queue.mark_rejected(draft_id)
    if ok:
        print(f"❌ Draft {draft_id} marked as rejected.")
    else:
        print(f"⚠️ Draft {draft_id} not found.")

def cmd_traffic():
    print_banner()
    from agents.performance_tracker import PerformanceTracker
    from daily_kpop_pipeline import load_config
    config = load_config()
    tracker = PerformanceTracker(config)
    traffic = tracker.get_click_view_statistics()
    print("📈 Today Traffic & Views Statistics:")
    print(f"  • Today Views (PV): {traffic.get('today_views', 0):,} PV")
    print(f"  • Today Uniques (UV): {traffic.get('today_uv', 0):,} UV")
    print(f"  • Reader Clicks: {traffic.get('today_clicks', 0):,} ({traffic.get('ctr', 0.0):.2f}% CTR)")
    print(f"  • Cumulative 14d Views: {traffic.get('cumulative_views', 0):,} PV")
    print(f"  • Total Blog Posts: {traffic.get('total_posts', 0)}")

def main():
    parser = argparse.ArgumentParser(description="K-Pop Hangul Blog Management CLI")
    parser.add_argument("action", choices=["status", "charts", "candidates", "run", "images", "queue", "approve", "reject", "traffic"], nargs="?", default="status",
                        help="Action to perform (status, charts, candidates, run, images, queue, approve, reject, traffic)")
    parser.add_argument("id", nargs="?", default=None, help="Draft ID for approve/reject")
    parser.add_argument("--count", type=int, default=1, help="Number of songs for pipeline run (default: 1)")

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
    elif args.action == "queue":
        cmd_queue()
    elif args.action == "approve":
        cmd_approve(args.id)
    elif args.action == "reject":
        cmd_reject(args.id)
    elif args.action == "traffic":
        cmd_traffic()

if __name__ == "__main__":
    main()

