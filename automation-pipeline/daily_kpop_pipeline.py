#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Daily K-Pop Korean Learning Pipeline:
1. Fetches real-time Melon Top 100 & Spotify Daily Charts
2. Selects fresh, unpublished top songs
3. Writes comprehensive English educational lessons (Hangul lyrics, Romanization, vocabulary, grammar)
4. Performs independent pedagogical editorial review (Gemini)
5. Generates SVG thumbnail & contextual article diagrams
6. Queues into DraftApprovalQueue (HITL Review Gate - wikidocs.net/366626)
7. Sends Telegram smart review report with approval button
8. Publishes ONLY when human-approved via Telegram button or /approve command
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
from integrations.github_publisher import GitHubPublisher
from integrations.telegram_bot import TelegramNotifier

FRONTEND_BLOG_DIR = os.path.join(ROOT_DIR, "blog-frontend", "src", "content", "blog")
CONFIG_FILE = os.path.join(ROOT_DIR, "blog.config.json")


def load_config() -> Dict[str, Any]:
    """Loads configuration by combining YAML config and blog.config.json."""
    cfg = {"blogId": "kpop-hangul"}
    yaml_path = os.path.join(SCRIPT_DIR, "config", "config.yaml")
    if os.path.exists(yaml_path):
        try:
            import yaml
            with open(yaml_path, "r", encoding="utf-8") as f:
                yaml_cfg = yaml.safe_load(f)
                if isinstance(yaml_cfg, dict):
                    cfg.update(yaml_cfg)
        except Exception:
            pass
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                json_cfg = json.load(f)
                if isinstance(json_cfg, dict):
                    cfg.update(json_cfg)
        except Exception:
            pass
    return cfg


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

    pub_date = article.get("pubDate") or datetime.now().strftime("%Y-%m-%d")

    frontmatter = {
        "title": article.get("title", "Learn Korean with K-Pop"),
        "description": article.get("description", "Master Korean lyrics, vocabulary and grammar."),
        "pubDate": pub_date,
        "heroImage": article.get("heroImage", f"/images/thumbnails/{slug}.svg"),
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
        "faqs": article.get("faqs", []),
        "draft": article.get("draft", False)
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


def publish_queued_draft(config: Dict[str, Any], draft_id: str, *, human_approved: bool = False) -> tuple:
    """
    검토 대기 큐(DraftApprovalQueue)의 특정 K-Pop 초안을 승인하여
    Astro 블로그 저장소에 마크다운 파일로 저장하고 Git 커밋/배포 및 텔레그램 알림 수행.
    (wikidocs.net/366626 HITL 필수 검수 게이트 원칙 준수)
    """
    queue = DraftApprovalQueue(ROOT_DIR)
    draft_item = queue.get_draft(draft_id)
    if not draft_item:
        return False, f"초안 ID '{draft_id}'를 찾을 수 없습니다."

    if draft_item.get("status") == "published":
        existing_url = draft_item.get("published_url", "")
        return True, f"이미 발행 완료된 글입니다: {existing_url}"

    if not human_approved:
        return False, "초안 본문과 감수 내용을 검토한 후 사람이 승인해야 발행할 수 있습니다."

    article = draft_item.get("article", {})
    song = draft_item.get("topic", {})
    review = draft_item.get("review", {})

    today_str = datetime.now().strftime("%Y-%m-%d")
    slug = draft_item.get("existing_slug") or article.get("slug") or generate_slug(
        article.get("artist", song.get("artist", "kpop")),
        article.get("songTitle", song.get("title", "song")),
        today_str
    )
    article["slug"] = slug
    article["draft"] = False

    # 1. Astro 마크다운 컨텐츠 저장
    post_path = save_markdown_post(article, slug)
    print(f"📄 Saved Astro Content: {os.path.relpath(post_path, ROOT_DIR)}")

    # 2. 발행 완료 곡 데이터베이스 등록
    save_published_song({
        "artist": article.get("artist", song.get("artist")),
        "songTitle": article.get("songTitle", song.get("title")),
        "title": article.get("title"),
        "slug": slug,
        "chartSource": article.get("chartSource", song.get("chartSource", "Melon Top 100")),
        "chartRank": article.get("chartRank", song.get("rank", 1)),
        "difficulty": article.get("difficulty", song.get("difficulty", "Beginner")),
        "genre": article.get("genre", song.get("genre", "Dance & Pop")),
        "pubDate": today_str,
        "score": review.get("total_score", 90),
        "heroImage": article.get("heroImage")
    })

    # 3. Git 커밋 & Push (GitHubPublisher 활용)
    site_url = config.get("site", {}).get("url", "https://kpop-hangul.github.io").rstrip("/")
    publisher = GitHubPublisher(config)
    full_post_url = f"{site_url}/blog/{slug}/"

    try:
        publisher._git_commit_and_push(post_path, article.get("title", slug), slug=slug)
    except Exception as e:
        print(f"⚠️ Git 작업 알림: {e}")

    # 4. 검토 큐 상태 갱신 (published)
    queue.mark_published(draft_id, slug, full_post_url)

    # 5. 텔레그램 배포 완료 알림
    telegram = TelegramNotifier(config)
    inspection = {
        "score": review.get("total_score", 90),
        "char_count": len(article.get("markdown_content", ""))
    }
    telegram.send_article_published(article, inspection, full_post_url)

    return True, full_post_url


def run_daily_pipeline(count: int = 1, specific_song: Optional[Dict[str, Any]] = None, dry_run: bool = False, auto_approve: bool = False):
    """Executes the daily generation workflow and queues drafts for human review."""
    print("=" * 75)
    print(" 🚀  K-Pop Hangul Daily Learning Lesson Pipeline (HITL Review Gate)")
    print(f" 📅  Execution Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 75)

    config = load_config()
    writer = ContentWriter(config)
    reviewer = EditorialReviewAgent(config)
    queue = DraftApprovalQueue(ROOT_DIR)
    telegram = TelegramNotifier(config)

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
        article["slug"] = slug

        if dry_run:
            print(f"🧪 [Dry Run] Generated article for '{slug}'. Score: {score}/100. Skipping queue write.")
            results.append({"slug": slug, "title": article.get("title"), "score": score, "status": "dry_run"})
            continue

        # Generate SVG thumbnail & contextual article illustrations
        try:
            from modules.thumbnail_generator import generate_thumbnail_for_post
            from modules.article_image_generator import generate_and_integrate_article_images

            post_data = {
                "slug": slug,
                "title": article.get("title", ""),
                "artist": article.get("artist", song.get("artist")),
                "songTitle": article.get("songTitle", song.get("title")),
                "hangulTitle": article.get("hangulTitle", ""),
                "difficulty": article.get("difficulty", "Beginner"),
                "genre": article.get("genre", "Dance & Pop"),
                "chartRank": article.get("chartRank", song.get("rank")),
                "chartSource": article.get("chartSource", song.get("chartSource")),
            }
            thumb_url = generate_thumbnail_for_post(post_data)
            article["heroImage"] = thumb_url
            print(f"  🖼️ Generated SVG Thumbnail: {thumb_url}")

            updated_content, imgs = generate_and_integrate_article_images(article, slug)
            article["markdown_content"] = updated_content
            article["article_images"] = imgs
            print(f"  📸 Injected {len(imgs)} contextual educational diagrams into lesson!")
        except Exception as e:
            print(f"  ⚠️ Thumbnail / Illustration generation warning: {e}")
            article["heroImage"] = f"/images/thumbnails/{slug}.svg"

        # 4. Save to DraftApprovalQueue for Human-in-the-Loop review
        draft_id = queue.add_draft(article, review, topic=song)
        print(f"📥 [Review Queue] Draft saved to queue: {draft_id} (pending human review)")

        # 5. Send Telegram review report with approval button
        telegram.send_review_report(draft_id, article, review)
        print(f"📲 Sent Telegram review report for {draft_id}")

        results.append({
            "slug": slug,
            "draft_id": draft_id,
            "title": article.get("title"),
            "artist": article.get("artist"),
            "score": score,
            "status": "pending_review"
        })

    if auto_approve:
        print("\n⚠️ 자동 승인은 지원하지 않습니다 (wikidocs.net/366626 저품질 방지 수칙).")
        print("   생성된 초안을 텔레그램 또는 CLI(/approve, manage_kpop.py approve)로 승인하세요.")

    # Summary Report
    print("\n" + "=" * 75)
    print(" 🎉  Daily K-Pop Korean Generation Summary (Draft Review Queue):")
    print("=" * 75)
    for r in results:
        print(f" • [{r.get('score', 0)}/100] {r.get('artist', '')} - {r.get('title')}")
        print(f"   Draft ID: {r.get('draft_id')} (Status: {r.get('status')})")
        print(f"   Approve via CLI: python3 manage_kpop.py approve {r.get('draft_id')}")
    print("\n✅ 초안 작성이 완료되어 검토 대기 큐에 안전하게 보관되었습니다!")
    print("   사람의 검토 및 승인 후에만 블로그에 최종 발행됩니다.\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Daily K-Pop Korean Lesson Automation Pipeline (HITL Review Gate)")
    parser.add_argument("--count", type=int, default=1, help="Number of songs to generate into draft queue (default: 1)")
    parser.add_argument("--artist", type=str, default="", help="Specific artist name")
    parser.add_argument("--title", type=str, default="", help="Specific song title")
    parser.add_argument("--dry-run", action="store_true", help="Run without writing files or queuing")
    parser.add_argument("--approve", action="store_true", help="호환 옵션: 자동 발행하지 않고 검토 큐에 저장")
    parser.add_argument("--publish-draft", type=str, default=None, help="대기 큐의 특정 draft_id 승인 및 발행")
    parser.add_argument("--reject-draft", type=str, default=None, help="대기 큐의 특정 draft_id 보류")
    parser.add_argument("--list-queue", action="store_true", help="대기 큐 목록 조회")
    parser.add_argument("--mode", type=str, default="auto", help="실행 모드")

    args = parser.parse_args()
    config = load_config()

    if args.list_queue:
        queue = DraftApprovalQueue(ROOT_DIR)
        pending = queue.list_pending()
        print(f"\n📋 [대기 중인 K-Pop 초안 큐 ({len(pending)}건)]")
        for d in pending:
            score = d.get("review", {}).get("total_score", "N/A")
            print(f"  • [{d['draft_id']}] ({d.get('created_at')}) {d.get('title')} - {score}점")
        sys.exit(0)

    if args.publish_draft:
        success, res = publish_queued_draft(config, args.publish_draft, human_approved=True)
        if success:
            print(f"🎉 성공적으로 발행되었습니다: {res}")
        else:
            print(f"❌ 발행 실패: {res}")
        sys.exit(0 if success else 1)

    if args.reject_draft:
        queue = DraftApprovalQueue(ROOT_DIR)
        ok = queue.mark_rejected(args.reject_draft)
        if ok:
            print(f"❌ 초안 {args.reject_draft} 보류 처리 완료")
        else:
            print(f"⚠️ 초안 {args.reject_draft} 찾을 수 없음")
        sys.exit(0)

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

    run_daily_pipeline(count=args.count, specific_song=custom_song, dry_run=args.dry_run, auto_approve=args.approve)
