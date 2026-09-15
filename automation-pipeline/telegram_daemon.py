import os
import glob
import json
import re
import time
import yaml
import logging
import subprocess
from datetime import datetime
from typing import Any, Dict, List, Optional
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

from integrations.telegram_bot import _load_env_file, TelegramNotifier
from integrations.antigravity_runner import AntigravityRunner
from agents.performance_tracker import PerformanceTracker
from modules.draft_queue import DraftApprovalQueue
from modules.agent_manager import AgentManager
from agents.editorial_reviewer import EditorialReviewAgent
from templates.prompt_templates import EDITORIAL_RULES
from daily_kpop_pipeline import load_config, publish_queued_draft
from agents.content_writer import ContentWriter
from agents.policy_inspector import PolicyInspector
from integrations.github_publisher import GitHubPublisher
from integrations.google_indexing import GoogleIndexing
import asyncio
from functools import wraps
from modules.approval_binding import issue_approval, consume_approval, invalidate_approvals

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

config = load_config()
_load_env_file()
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
SITE_TITLE = config.get("site", {}).get("title", "K-Pop 한글 (K-Pop Hangul)")
SITE_URL = config.get("site", {}).get("url", "https://kpop-hangul.github.io").rstrip("/")

# Chat session storage: { chat_id: { "state": ..., "topic": ..., "draft": ..., "slug": ..., "feedbacks": [...], "busy": ..., "action": ... } }
sessions = {}

raw_content_dir = config.get("github", {}).get("blog_content_dir", "../blog-frontend/src/content/blog")
CONTENT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), raw_content_dir))

def configured_chat_id():
    value = config.get("telegram", {}).get("chat_id") or os.getenv("TELEGRAM_CHAT_ID")
    if isinstance(value, bool) or not re.fullmatch(r"-?\d+", str(value or "").strip()):
        return None
    return int(str(value).strip())


def require_allowed_chat(handler):
    """One fail-closed boundary for every command/message/callback handler."""
    @wraps(handler)
    async def guarded(update, context):
        allowed = configured_chat_id()
        actual = getattr(getattr(update, "effective_chat", None), "id", None)
        if allowed is None or actual != allowed:
            logger.warning("Rejected Telegram update outside the configured chat.")
            return
        current = sessions.get(actual, {})
        readonly = {"handle_help_command", "handle_status_command", "handle_queue_command", "handle_review_command", "handle_traffic_command", "start", "handle_delete_command", "handle_agent_command"}
        if current.get("publication_inflight") and handler.__name__ not in readonly:
            return
        return await handler(update, context)
    return guarded


def extract_json(raw_text: str) -> Any:
    clean = raw_text.strip()
    clean = re.sub(r"^```json\s*", "", clean, flags=re.MULTILINE)
    clean = re.sub(r"^```\s*", "", clean, flags=re.MULTILINE)
    clean = re.sub(r"\s*```$", "", clean, flags=re.MULTILINE)
    
    # 1. Direct parse
    try:
        return json.loads(clean)
    except Exception:
        pass
    
    # 2. Try JSON Array [ ... ] (다중 글 / 시리즈 목록)
    list_match = re.search(r"\[[\s\S]*\]", clean)
    if list_match:
        try:
            return json.loads(list_match.group(0))
        except Exception:
            pass
            
    # 3. Try JSON Object { ... } (단일 글)
    dict_match = re.search(r"\{[\s\S]*\}", clean)
    if dict_match:
        try:
            return json.loads(dict_match.group(0))
        except Exception:
            pass
            
    raise ValueError(f"유효한 JSON 데이터를 추출하지 못했습니다:\n{raw_text[:200]}")

def fetch_url_context(url: str) -> str:
    """사용자가 전송한 웹 링크의 본문 및 목차 요약 발췌"""
    try:
        from curl_cffi import requests
        from bs4 import BeautifulSoup
        r = requests.get(url, impersonate="chrome120", timeout=12)
        if r.status_code != 200:
            return f"(URL 접근 실패 HTTP {r.status_code})"
        soup = BeautifulSoup(r.text, "html.parser")
        title = soup.title.string.strip() if soup.title else ""
        
        # 목차 및 헤딩 수집
        headings = [h.get_text(strip=True) for h in soup.find_all(["h1", "h2", "h3"])][:15]
        headings_text = "\n".join([f"- {h}" for h in headings if len(h) > 2])

        # 주요 텍스트 본문 추출
        text_body = soup.get_text(separator=" ", strip=True)[:2500]
        
        return f"""
[참고 URL 원문 발췌 데이터: {url}]
- 페이지 제목: {title}
- 주요 목차 및 챕터:
{headings_text}
- 주요 본문 내용 요약:
{text_body}
"""
    except Exception as e:
        logger.warning(f"URL 내용 수집 실패 ({url}): {e}")
        return ""

@require_allowed_chat
async def handle_help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = f"""📚 <b>[{SITE_TITLE} 블로그 에이전트 명령어 & 사용 가이드]</b>
━━━━━━━━━━━━━━━━━━━━
🤖 <b>기본 명령어 목록:</b>

• <code>/agent</code> : 라즈베리파이 자동화 에이전트 관제 (스케줄 확인, 시작/중지, 즉시실행)
• <code>/traffic</code> (또는 <code>/views</code>, <code>/clicks</code>) : 오늘 실시간 클릭수 및 뷰(PV/UV) 트래픽 보고서 즉시 조회
• <code>/status</code> : 라즈베리파이 상태, 타이머 스케줄, 대기 큐 및 세션 조회
• <code>/queue</code> : 발행 대기 중인 초안 큐 목록 및 감수 점수 조회
• <code>/approve [ID]</code> : 특정 초안 승인 및 GitHub Pages 즉시 배포
• <code>/reject [ID]</code> : 특정 초안 발행 보류(반려) 처리
• <code>/review [ID]</code> : 특정 초안의 AI 편집 의견과 검토 상태 조회
• <code>/write [주제/자료]</code> : 새로운 블로그 포스팅 기획 및 작성 시작
• <code>/edit [URL] [요청사항]</code> : 기존 블로그 포스팅 내용 또는 URL(슬러그) 수정
• <code>/delete [슬러그]</code> : 발행된 블로그 글 영구 삭제 (마크다운+이미지+썸네일)
• <code>/cancel</code> 또는 <code>/reset</code> : 진행 중인 기획/초안 작업 취소 및 초기화
• <code>/help</code> : 사용 가능한 명령어 목록 및 사용 가이드 보기

━━━━━━━━━━━━━━━━━━━━
💡 <b>명령어 없이 자연어로 바로 쓰기:</b>

1. <b>새 글 작성:</b>
   • 주제, 뉴스 기사 URL, 유튜브 요약본 등을 채팅창에 그대로 전송
   • <i>기획안 확인 후 [본문 초안 작성] 또는 [즉시 발행] 선택</i>

2. <b>대화형 첨언 및 본문 보강:</b>
   • 기획안이나 초안 단계에서 추가하고 싶은 내용을 메시지로 계속 전송하면 실시간으로 본문에 반영

3. <b>기존 글 수정:</b>
   • <code>{SITE_URL}/blog/...</code> 링크와 함께 수정할 내용을 입력"""

    await update.message.reply_text(msg, parse_mode="HTML")

@require_allowed_chat
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"👋 <b>{SITE_TITLE} 인터랙티브 블로그 AI 에이전트에 오신 것을 환영합니다!</b>\n\n"
        "자유롭게 작성하고 싶은 <b>주제</b>나 <b>참고 링크/자료</b>를 채팅창에 보내주시면 글 작성이 시작됩니다.\n\n"
        "전체 명령어 및 사용 방법이 궁금하시면 언제든 <code>/help</code> 를 입력해 주세요! 🚀",
        parse_mode="HTML"
    )

@require_allowed_chat
async def handle_traffic_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """오늘 실시간 클릭 및 뷰(View) 트래픽 보고서 즉시 조회 및 전송"""
    status_msg = await update.message.reply_text("⏳ <b>실시간 트래픽 및 클릭/뷰 데이터를 집계 중입니다...</b>", parse_mode="HTML")
    try:
        tracker = PerformanceTracker(config)
        traffic_data = tracker.get_click_view_statistics()
        notifier = TelegramNotifier(config)
        report_msg = notifier.generate_click_view_report_text(traffic_data)
        try:
            await status_msg.edit_text(report_msg, parse_mode="HTML", disable_web_page_preview=True)
        except Exception:
            await update.message.reply_text(report_msg, parse_mode="HTML", disable_web_page_preview=True)
    except Exception as e:
        logger.error(f"트래픽 보고서 생성 실패: {e}")
        await update.message.reply_text(f"⚠️ 트래픽 보고서 생성 중 오류가 발생했습니다: {e}")

@require_allowed_chat
async def handle_status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    tracker = PerformanceTracker(config)
    runner = AntigravityRunner(config)
    
    # 1. System Health
    health = tracker.get_system_health()
    cpu_temp = health.get("cpu_temp", "48.0°C")
    disk_free = health.get("disk_free", "1.7TB")
    
    # 2. Site statistics
    stats = tracker.get_site_statistics()
    total_posts = stats.get("total_posts", 0)
    today_posts = stats.get("today_posts", 0)
    
    # 3. Latest published post
    latest_post_info = "없음"
    latest_post_url = ""
    try:
        md_files = glob.glob(os.path.join(CONTENT_DIR, "*.md"))
        if md_files:
            latest_file = max(md_files, key=os.path.getmtime)
            latest_slug = os.path.splitext(os.path.basename(latest_file))[0]
            with open(latest_file, "r", encoding="utf-8") as f:
                content = f.read()
                title_match = re.search(r"^title:\s*(.+)$", content, re.MULTILINE)
                latest_title = title_match.group(1).strip("'\"") if title_match else latest_slug
            site_url = SITE_URL
            latest_post_url = f"{site_url.rstrip('/')}/blog/{latest_slug}/"
            latest_post_info = f"<b>{latest_title}</b>"
    except Exception:
        pass

    # 4. Engine & CLI status
    cli_path = runner.get_cli_path()
    engine_status = f"🟢 정상 연동 (<code>{cli_path}</code>)" if cli_path else "🔴 CLI 미발견"

    # 5. Scheduled Timers (parse systemctl list-timers)
    timer_details = []
    try:
        res = subprocess.run(["systemctl", "--user", "list-timers", "--no-pager"], capture_output=True, text=True, timeout=5)
        lines = res.stdout.strip().split("\n")
        for line in lines:
            if "auto-blog-kpop-pipeline.timer" in line:
                timer_details.append("  • 🎵 <b>K-Pop 한글 일일 포스팅</b>: 매일 <code>13:15 KST</code>")
            elif "auto-blog.timer" in line:
                timer_details.append("  • 🤖 <b>앱시안 일일 포스팅</b>: 매일 <code>11:10 KST</code>")
            elif "auto-blog-goldenlife-pipeline.timer" in line:
                timer_details.append("  • 👵 <b>골든라이프 포스팅</b>: 매일 <code>09:20 KST</code>")
            elif "auto-blog-morning.timer" in line:
                timer_details.append("  • 🌅 <b>아침 현황 브리핑</b>: 매일 <code>08:00 KST</code>")
            elif "auto-blog-evening.timer" in line:
                timer_details.append("  • 🌆 <b>저녁 트래픽 리포트</b>: 매일 <code>19:00 KST</code>")
            elif "auto-blog-health.timer" in line:
                timer_details.append("  • 🍓 <b>라즈베리파이 헬스체크</b>: 매일 <code>12:00 KST</code>")
            elif "auto-blog-dryrun.timer" in line:
                timer_details.append("  • 🩺 <b>이상 탐지 (Dryrun)</b>: <code>매일 06:30 KST</code>")
    except Exception:
        pass
    
    if not timer_details:
        timer_details = [
            "  • 🎵 K-Pop 한글 일일 포스팅: 매일 13:15 KST",
            "  • 🌅 아침 08:00 브리핑 / 🌆 저녁 19:00 트래픽 리포트",
            "  • 🍓 매일 12:00 라즈베리파이 헬스체크"
        ]

    timers_text = "\n".join(timer_details)

    # 6. Current Interactive Session Status for this User
    session = sessions.get(chat_id)
    if not session:
        session_text = "💤 <b>대기 중 (IDLE)</b>\n  <i>새 글 작성을 원하시면 주제나 링크를 보내주세요.</i>"
    else:
        if session.get("busy"):
            action = session.get("action", "AI 작업 수행 중")
            elapsed = int(time.time() - session.get("started_at", time.time()))
            session_text = f"⏳ <b>[실시간 AI 작업 진행 중 ({elapsed}초 경과)]</b>\n  ⚡ <b>현재 작업</b>: {action}\n  <i>잠시만 기다려주시면 완료 메시지가 전송됩니다.</i>"
        else:
            state = session.get("state", "IDLE")
            if state == "PLANNING":
                topic_title = session.get("topic", {}).get("title", "주제 기획 중")
                session_text = f"🎯 <b>[기획안 검토/첨언 대기 중]</b>\n  📌 주제: <b>{topic_title}</b>"
            elif state == "DRAFTED":
                draft_title = session.get("draft", {}).get("title", "초안 작성 완료")
                session_text = f"✍️ <b>[초안 수정/배포 대기 중]</b>\n  📌 제목: <b>{draft_title}</b>"
            elif state == "EDITING":
                edit_title = session.get("data", {}).get("title", session.get("slug", "수정 중"))
                session_text = f"✏️ <b>[기존 포스팅 수정 대기 중]</b>\n  📌 대상: <code>{session.get('slug')}</code>"
            else:
                session_text = f"⚙️ <b>진행 중 ({state})</b>"

    # Keywords Queue Status
    csv_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "data", "keywords.csv"))
    queue_summary = "등록된 큐 없음"
    if os.path.exists(csv_path):
        try:
            import csv
            with open(csv_path, "r", encoding="utf-8") as f:
                r_list = list(csv.DictReader(f))
                ready_c = len([r for r in r_list if r.get("status") == "ready"])
                next_kw = next((r.get("keyword") for r in r_list if r.get("status") == "ready"), "없음")
                queue_summary = f"대기 <b>{ready_c}개</b> / 총 {len(r_list)}개 (다음: <i>{next_kw[:16]}...</i>)"
        except Exception:
            pass

    # Draft Approval Queue Status
    draft_queue = DraftApprovalQueue()
    pending_drafts = draft_queue.list_pending()
    draft_queue_summary = f"<b>{len(pending_drafts)}건 대기 중</b> (명령어: <code>/queue</code>)" if pending_drafts else "대기 중인 초안 없음 (0건)"

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    msg = f"""📊 <b>[{SITE_TITLE} 블로그 에이전트 시스템 현황]</b> ({now_str})
━━━━━━━━━━━━━━━━━━━━
🍓 <b>라즈베리파이 5 서버 상태</b>
  • 🌡️ CPU 온도: <b>{cpu_temp}</b>
  • 💾 저장 공간: <b>{disk_free}</b>
  • ⚡ AI 엔진: {engine_status}
  • 🤖 텔레그램 데몬: <b>🟢 24/7 실시간 가동 중</b>

⏰ <b>자동화 에이전트 스케줄</b>
{timers_text}

📚 <b>블로그 콘텐츠 & 대기 큐</b>
  • 총 포스트 수: <b>{total_posts}개</b> (+{today_posts}건 오늘 발행)
  • 📥 <b>검토 대기 큐</b>: {draft_queue_summary}
  • 📋 고단가 롱테일 큐: {queue_summary}
  • 최근 발행 글: {latest_post_info}

💬 <b>내 대화 세션 상태</b>
  • {session_text}"""

    keyboard = []
    if latest_post_url:
        keyboard.append([InlineKeyboardButton("🌐 최근 발행 글 보기", url=latest_post_url)])
    keyboard.append([InlineKeyboardButton("🏠 블로그 메인 홈", url=SITE_URL)])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(msg, parse_mode="HTML", reply_markup=reply_markup, disable_web_page_preview=True)

@require_allowed_chat
async def handle_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id in sessions:
        del sessions[chat_id]
        await update.message.reply_text("🔄 현재 작업 세션이 취소 및 초기화되었습니다. 새로운 주제를 언제든 입력해주세요!")

@require_allowed_chat
async def handle_queue_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    queue = DraftApprovalQueue()
    pending = queue.list_pending()
    if not pending:
        await update.message.reply_text("📋 <b>현재 승인 대기 중인 초안이 없습니다.</b>\n새 글이 작성되면 이곳에 누적됩니다.", parse_mode="HTML")
        return
        
    msg_lines = [f"📋 <b>[{SITE_TITLE} 검토 대기 큐 목록 ({len(pending)}건)]</b>\n━━━━━━━━━━━━━━━━━━━━"]
    keyboard = []
    
    for idx, d in enumerate(pending[:5], 1):
        draft_id = d.get("draft_id", "")
        title = d.get("title", "제목 없음")
        score = d.get("review", {}).get("total_score", 0)
        verdict = d.get("review", {}).get("verdict", "UNKNOWN")
        created = d.get("created_at", "")[:16]
        
        msg_lines.append(
            f"<b>{idx}. {title}</b>\n"
            f"  • ID: <code>{draft_id}</code>\n"
            f"  • 감수 점수: <b>{score}점</b> ({verdict}) | 📅 {created}\n"
        )
        keyboard.append([
            InlineKeyboardButton(f"✅ 승인 #{idx}", callback_data=f"approve:{draft_id}"),
            InlineKeyboardButton(f"✏️ 수정 #{idx}", callback_data=f"edit_draft:{draft_id}"),
            InlineKeyboardButton(f"📖 초안 #{idx}", callback_data=f"view_draft:{draft_id}"),
            InlineKeyboardButton(f"❌ 보류 #{idx}", callback_data=f"reject:{draft_id}")
        ])
        
    msg_lines.append("━━━━━━━━━━━━━━━━━━━━\n💡 <i>버튼을 누르거나 <code>/approve &lt;ID&gt;</code>, <code>/edit &lt;ID&gt;</code> 로 관리할 수 있습니다.</i>")
    reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None
    await update.message.reply_text("\n".join(msg_lines), parse_mode="HTML", reply_markup=reply_markup)

@require_allowed_chat
async def handle_approve_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    queue = DraftApprovalQueue()
    if not args:
        pending = queue.list_pending()
        if not pending:
            await update.message.reply_text("⚠️ 대기 중인 초안이 없습니다.")
            return
        elif len(pending) == 1:
            draft_id = pending[0]["draft_id"]
        else:
            draft_list_text = "\n".join([f"• <code>{d['draft_id']}</code>: {d['title']}" for d in pending[:5]])
            await update.message.reply_text(
                f"⚠️ 승인할 초안 ID를 입력해주세요:\n<code>/approve &lt;draft_id&gt;</code>\n\n대기 목록:\n{draft_list_text}",
                parse_mode="HTML"
            )
            return
    else:
        draft_id = args[0]
        
    draft = queue.get_draft(draft_id)
    if not draft:
        await update.message.reply_text(f"❌ 초안 ID '{draft_id}'를 찾을 수 없습니다.")
        return
        
    status_msg = await update.message.reply_text(
        f"🚀 <b>초안('{draft.get('title')}') 승인 완료!</b>\nGitHub Pages에 배포를 진행 중입니다...",
        parse_mode="HTML"
    )
    
    success, res = publish_queued_draft(config, draft["draft_id"], human_approved=True)
    if success:
        await status_msg.edit_text(
            f"🎉 <b>[포스팅 승인 및 저장소 반영 요청 완료]</b>\n━━━━━━━━━━━━━━━━━━━━\n"
            f"📌 <b>제목</b>: <b>{draft.get('title')}</b>\n"
            f"🔗 <b>글 바로가기</b>: <a href=\"{res}\">{res}</a>\n\n"
            f"✨ <i>저장소 반영 요청이 완료되었습니다. Pages 배포 결과와 실제 URL을 확인하세요.</i>",
            parse_mode="HTML",
            disable_web_page_preview=False
        )
    else:
        await status_msg.edit_text(f"❌ 배포 실패: {res}")

@require_allowed_chat
async def handle_reject_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    queue = DraftApprovalQueue()
    if not args:
        await update.message.reply_text("⚠️ 보류할 초안 ID를 입력해주세요:\n<code>/reject &lt;draft_id&gt;</code>", parse_mode="HTML")
        return
    draft_id = args[0]
    ok = queue.mark_rejected(draft_id)
    if ok:
        await update.message.reply_text(f"❌ 초안(<code>{draft_id}</code>)이 보류 처리되었습니다.", parse_mode="HTML")
    else:
        await update.message.reply_text(f"⚠️ 초안(<code>{draft_id}</code>)을 찾을 수 없습니다.", parse_mode="HTML")

@require_allowed_chat
async def handle_delete_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """발행된 블로그 글 삭제"""
    import urllib.parse
    args = context.args
    target_text = " ".join(args).strip() if args else ""
    
    if not target_text:
        # Show recent posts list for selection
        try:
            md_files = sorted(glob.glob(os.path.join(CONTENT_DIR, "*.md")), key=os.path.getmtime, reverse=True)[:10]
            if not md_files:
                await update.message.reply_text("📋 삭제할 수 있는 게시글이 없습니다.")
                return
            msg_lines = [f"🗑️ <b>[{SITE_TITLE} 삭제 가능한 최근 게시글 목록]</b>\n━━━━━━━━━━━━━━━━━━━━"]
            keyboard = []
            for idx, fp in enumerate(md_files[:6], 1):
                slug = os.path.splitext(os.path.basename(fp))[0]
                with open(fp, "r", encoding="utf-8") as f:
                    content = f.read()
                title_match = re.search(r"^title:\s*(.+)$", content, re.MULTILINE)
                title = title_match.group(1).strip("'\"") if title_match else slug
                msg_lines.append(f"<b>{idx}.</b> {title}\n  • <code>{slug}</code>")
                keyboard.append([InlineKeyboardButton(f"🗑️ #{idx} 삭제: {title[:18]}...", callback_data=f"delete_confirm:{slug}")])
            msg_lines.append("\n━━━━━━━━━━━━━━━━━━━━\n💡 <i>삭제할 글의 버튼을 누르거나 슬러그/링크를 직접 입력하세요:</i>\n<code>/delete &lt;slug 또는 URL&gt;</code>")
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text("\n".join(msg_lines), parse_mode="HTML", reply_markup=reply_markup)
        except Exception as e:
            await update.message.reply_text(f"⚠️ 게시글 목록 조회 중 오류: {e}")
        return
    
    # Extract slug from full URL or text
    raw_input = urllib.parse.unquote(target_text)
    url_match = re.search(r"blog/([^/\s?#]+)", raw_input)
    if url_match:
        slug = url_match.group(1).rstrip("/")
    else:
        slug = raw_input.strip().strip("/").split()[-1]
    
    filepath = os.path.join(CONTENT_DIR, f"{slug}.md")
    if not os.path.exists(filepath):
        # 1. Prefix match
        matched = [f for f in os.listdir(CONTENT_DIR) if f.startswith(slug) and f.endswith(".md")]
        # 2. Substring match
        if not matched:
            matched = [f for f in os.listdir(CONTENT_DIR) if slug.lower() in f.lower() and f.endswith(".md")]
        
        if len(matched) == 1:
            slug = os.path.splitext(matched[0])[0]
            filepath = os.path.join(CONTENT_DIR, matched[0])
        elif len(matched) > 1:
            keyboard = []
            msg_lines = [f"🔍 <b>'{slug}' 검색 결과 여러 글이 발견되었습니다:</b>\n━━━━━━━━━━━━━━━━━━━━"]
            for idx, mf in enumerate(matched[:5], 1):
                s = os.path.splitext(mf)[0]
                with open(os.path.join(CONTENT_DIR, mf), "r", encoding="utf-8") as f:
                    c = f.read()
                tm = re.search(r"^title:\s*(.+)$", c, re.MULTILINE)
                t = tm.group(1).strip("'\"") if tm else s
                msg_lines.append(f"<b>{idx}.</b> {t} (<code>{s}</code>)")
                keyboard.append([InlineKeyboardButton(f"🗑️ #{idx} 삭제 선택", callback_data=f"delete_confirm:{s}")])
            keyboard.append([InlineKeyboardButton("❌ 취소", callback_data="btn_cancel_session")])
            await update.message.reply_text("\n".join(msg_lines), parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))
            return
        else:
            await update.message.reply_text(f"❌ 해당 게시글(<code>{slug}</code>)을 찾을 수 없습니다.\n<code>/delete</code> 만 입력하시면 최근 글 목록을 확인하실 수 있습니다.", parse_mode="HTML")
            return
    
    # Read title for confirmation
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
    title_match = re.search(r"^title:\s*(.+)$", content, re.MULTILINE)
    title = title_match.group(1).strip("'\"") if title_match else slug
    
    await update.message.reply_text(
        f"⚠️ <b>[글 삭제 최종 확인]</b>\n━━━━━━━━━━━━━━━━━━━━\n"
        f"📌 <b>제목</b>: <b>{title}</b>\n"
        f"🔗 <b>슬러그</b>: <code>{slug}</code>\n\n"
        f"⚠️ <i>이 작업은 되돌릴 수 없습니다. 마크다운 파일, 썸네일, 본문 이미지가 완전히 삭제되고 Git에 반영됩니다.</i>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🗑️ 확인 - 영구 삭제", callback_data=f"delete_execute:{slug}")],
            [InlineKeyboardButton("❌ 취소", callback_data="btn_cancel_session")]
        ])
    )

def format_agent_dashboard(mgr: AgentManager) -> (str, InlineKeyboardMarkup):
    agents = mgr.list_all_agents()
    lines = [
        "⚙️ <b>[라즈베리파이 5 자동화 에이전트 관제센터]</b>",
        "━━━━━━━━━━━━━━━━━━━━",
        "💡 <i>시스템 스케줄 타이머와 백그라운드 파이프라인 실시간 제어</i>\n"
    ]
    
    keyboard = []
    row = []
    for idx, a in enumerate(agents, 1):
        status_badge = "🟢 활성" if a["timer_active"] else "🔴 중지"
        time_info = a["left_time"] or a["next_run"]
        lines.append(f"<b>{idx}.</b> {a['icon']} <b>{a['name']}</b>\n   └ 상태: {status_badge} | ⏱️ <code>{time_info}</code>")
        
        btn_text = f"{a['icon']} {a['name'].split()[0]}"
        row.append(InlineKeyboardButton(btn_text, callback_data=f"agent_view:{a['key']}"))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    
    keyboard.append([InlineKeyboardButton("🔄 현황 새로고침", callback_data="agent_list")])
    lines.append("\n━━━━━━━━━━━━━━━━━━━━\n👇 <i>제어할 에이전트를 아래 버튼에서 선택하세요:</i>")
    return "\n".join(lines), InlineKeyboardMarkup(keyboard)

def format_agent_detail(mgr: AgentManager, key: str) -> (str, InlineKeyboardMarkup):
    st = mgr.get_agent_status(key)
    if not st:
        return "❌ 에이전트 정보를 찾을 수 없습니다.", InlineKeyboardMarkup([[InlineKeyboardButton("🔙 목록", callback_data="agent_list")]])
    
    timer_badge = "🟢 활성 (ACTIVE)" if st["timer_active"] else "🔴 일시중지 (INACTIVE)"
    svc_badge = "⚡ 실행 중 (RUNNING)" if st["service_active"] else "💤 대기 중 (IDLE)"
    
    text = f"""{st['icon']} <b>[에이전트 제어] {st['name']}</b>
━━━━━━━━━━━━━━━━━━━━
📝 <b>설명</b>: {st['desc']}
⏰ <b>타이머</b>: <code>{st['timer']}</code>
⚙️ <b>서비스</b>: <code>{st['service']}</code>

📊 <b>현재 상태</b>:
  • 스케줄 타이머: <b>{timer_badge}</b>
  • 서비스 상태: <b>{svc_badge}</b>
  • 다음 실행 예정: <code>{st['next_run']}</code> ({st['left_time'] or '대기'})

━━━━━━━━━━━━━━━━━━━━
👇 <b>원하시는 작업을 선택하세요:</b>"""

    keyboard = [
        [InlineKeyboardButton("🚀 지금 즉시 실행 (Run Now)", callback_data=f"agent_run:{key}")],
    ]
    if st["timer_active"]:
        keyboard.append([InlineKeyboardButton("⏸️ 스케줄 타이머 일시중지", callback_data=f"agent_stop:{key}")])
    else:
        keyboard.append([InlineKeyboardButton("▶️ 스케줄 타이머 시작", callback_data=f"agent_start:{key}")])
    
    keyboard.append([
        InlineKeyboardButton("🔄 타이머 재시작", callback_data=f"agent_restart:{key}"),
        InlineKeyboardButton("🔙 에이전트 목록", callback_data="agent_list")
    ])
    return text, InlineKeyboardMarkup(keyboard)

@require_allowed_chat
async def handle_agent_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """라즈베리파이 5 자동화 에이전트 관리 및 스케줄 제어"""
    mgr = AgentManager()
    args = context.args
    
    if not args:
        text, reply_markup = format_agent_dashboard(mgr)
        await update.message.reply_text(text, parse_mode="HTML", reply_markup=reply_markup)
        return
    
    action = args[0].lower()
    target_key = args[1].lower() if len(args) > 1 else None
    
    if action == "list":
        text, reply_markup = format_agent_dashboard(mgr)
        await update.message.reply_text(text, parse_mode="HTML", reply_markup=reply_markup)
        return
        
    if not target_key:
        await update.message.reply_text("⚠️ 대상 에이전트 키를 입력해주세요.\n예: <code>/agent start morning</code>, <code>/agent run goldenlife</code>", parse_mode="HTML")
        return
        
    if action == "start":
        ok, res_msg = mgr.start_agent(target_key)
        await update.message.reply_text(res_msg, parse_mode="HTML")
    elif action == "stop":
        ok, res_msg = mgr.stop_agent(target_key)
        await update.message.reply_text(res_msg, parse_mode="HTML")
    elif action == "restart":
        ok, res_msg = mgr.restart_agent(target_key)
        await update.message.reply_text(res_msg, parse_mode="HTML")
    elif action in ("run", "trigger"):
        ok, res_msg = mgr.trigger_run_now(target_key)
        await update.message.reply_text(res_msg, parse_mode="HTML")
    else:
        await update.message.reply_text(f"⚠️ 알 수 없는 액션: {action}\n(가능 액션: list, start, stop, restart, run)", parse_mode="HTML")

@require_allowed_chat
async def handle_review_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    queue = DraftApprovalQueue()
    if not args:
        await update.message.reply_text("⚠️ 조회할 초안 ID를 입력해주세요:\n<code>/review &lt;draft_id&gt;</code>", parse_mode="HTML")
        return
    draft_id = args[0]
    draft = queue.get_draft(draft_id)
    if not draft:
        await update.message.reply_text(f"⚠️ 초안(<code>{draft_id}</code>)을 찾을 수 없습니다.", parse_mode="HTML")
        return
        
    notifier = TelegramNotifier(config)
    notifier.send_review_report(draft["draft_id"], draft.get("article", {}), draft.get("review", {}))
    await update.message.reply_text(f"🧐 초안(<code>{draft_id}</code>)의 감수 보고서를 전송했습니다.", parse_mode="HTML")

@require_allowed_chat
async def handle_write_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = " ".join(context.args) if context.args else ""
    if not user_text:
        await update.message.reply_text("⚠️ 작성할 주제나 자료를 입력해주세요.\n예: /write 최근 AI 트렌드")
        return
    # Reset existing session and start new planning
    chat_id = update.effective_chat.id
    sessions[chat_id] = {"state": "PLANNING", "feedbacks": [user_text]}
    await generate_or_update_topic_plan(update.message, chat_id, user_text, context, is_update=False)

@require_allowed_chat
async def handle_edit_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = " ".join(context.args) if context.args else ""
    if not user_text:
        await update.message.reply_text(f"⚠️ 수정할 블로그 글 URL과 수정 요청사항을 함께 입력해주세요.\n예: /edit {SITE_URL}/blog/2026-09-03-senior-welfare-benefits-guide/ 제목 변경해줘")
        return
    await route_message(update.message, user_text, context)

@require_allowed_chat
async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    await route_message(update.message, user_text, context)

async def route_message(message, user_text, context):
    chat_id = message.chat_id
    session = sessions.get(chat_id)
    if session and session.get("busy"):
        return
    if session:
        invalidate_approvals(session)

    # 0. Delete Request Detection (자연어 삭제 감지)
    stripped = user_text.strip()
    if stripped.startswith("/delete") or any(kw in stripped for kw in ["글 삭제", "포스트 삭제", "게시글 삭제", "글삭제", "포스팅 삭제"]) or stripped == "삭제":
        clean_arg = re.sub(r"(?:/delete|글\s*삭제(?:해줘)?|포스트\s*삭제(?:해줘)?|게시글\s*삭제(?:해줘)?|삭제(?:해줘)?)", "", stripped).strip()
        class DummyContext:
            args = clean_arg.split() if clean_arg else []
        class DummyUpdate:
            effective_chat = message.chat
            class Msg:
                def __init__(self, m):
                    self.reply_text = m.reply_text
            message = Msg(message)
        await handle_delete_command(DummyUpdate(), DummyContext())
        return

    # 0-1. Agent & Scheduler Management Detection (자연어 에이전트/스케줄 감지)
    if stripped.startswith("/agent") or any(kw in stripped for kw in ["에이전트 관리", "스케줄 관리", "타이머 관리", "에이전트", "스케줄러"]):
        class DummyContext:
            args = []
        class DummyUpdate:
            effective_chat = message.chat
            class Msg:
                def __init__(self, m):
                    self.reply_text = m.reply_text
            message = Msg(message)
        await handle_agent_command(DummyUpdate(), DummyContext())
        return

    # 0-2. Queue Draft Direct Editing Session Feedback
    if session and session.get("state") == "QUEUE_DRAFT_EDITING":
        session.setdefault("feedbacks", []).append(user_text)
        await refine_queued_draft(message, chat_id, user_text, context)
        return

    # 1-0. Draft Queue Direct Edit Request by ID (e.g. /edit draft_... or 초안 수정 draft_...)
    draft_match = re.search(r"draft_\d+_[a-zA-Z0-9가-힣]+", user_text)
    if (user_text.strip().startswith("/edit") or "초안 수정" in user_text) and draft_match:
        target_draft_id = draft_match.group(0)
        await start_queue_draft_edit(message, chat_id, target_draft_id, context)
        return

    # 1. Existing Blog Edit Request
    blog_url_match = re.search(r"(?:https?://[^/\s]+/)?blog/([^/\s?#]+)", user_text)
    if blog_url_match or user_text.strip().startswith("/edit"):
        sessions[chat_id] = {"state": "EDITING", "feedbacks": [user_text]}
        await process_edit_input(message, user_text, blog_url_match, context)
        return

    # 2. In-Progress Planning Session Feedback (User adds remarks to Topic Plan)
    if session and session.get("state") == "PLANNING":
        session["feedbacks"].append(user_text)
        await generate_or_update_topic_plan(message, chat_id, user_text, context, is_update=True)
        return

    # 3. In-Progress Draft Session Feedback (User adds remarks to Article Draft)
    if session and session.get("state") == "DRAFTED":
        session["feedbacks"].append(user_text)
        await refine_article_draft(message, chat_id, user_text, context)
        return

    # 4. In-Progress Editing Session Feedback (User adds more instructions to existing post edit)
    if session and session.get("state") == "EDITING":
        session["feedbacks"].append(user_text)
        await process_edit_input(message, user_text, None, context, is_update=True)
        return

    # 5. Brand New Creation Session (No active session)
    sessions[chat_id] = {"state": "PLANNING", "feedbacks": [user_text]}
    await generate_or_update_topic_plan(message, chat_id, user_text, context, is_update=False)

# -------------------------------------------------------------
# STEP 1: TOPIC PLANNING & ITERATIVE REFINEMENT
# -------------------------------------------------------------
async def generate_or_update_topic_plan(message, chat_id, user_input, context, is_update=False):
    if chat_id in sessions:
        invalidate_approvals(sessions[chat_id])
    loading_text = "🔄 추가 첨언 및 자료를 반영하여 기획안을 보강 중입니다..." if is_update else "⏳ 입력하신 자료를 분석하여 포스팅 기획안을 작성 중입니다. (Antigravity CLI 가동 중...)"
    processing_msg = await message.reply_text(loading_text)

    session = sessions.get(chat_id, {})
    session["busy"] = True
    session["action"] = "포스팅 기획안 업데이트 중" if is_update else "새 글 포스팅 기획안 작성 (Antigravity CLI)"
    session["started_at"] = time.time()
    sessions[chat_id] = session

    current_topic = session.get("topic")
    feedbacks = session.get("feedbacks", [user_input])

    try:
        runner = AntigravityRunner(config)
        category_names = ", ".join(c.get("name", "") for c in config.get("content", {}).get("categories", []))
        system_prompt = f"주제별 독자 질문에 답하는 블로그 기획 보조입니다. 등록 카테고리: {category_names}. 기획 JSON 형식만 반환하세요."

        # URL 링크가 포함된 경우 웹페이지 본문 및 목차 자동 수집
        url_match = re.search(r"https?://[^\s]+", user_input)
        url_context = ""
        if url_match:
            raw_url = url_match.group(0).rstrip(".,)")
            if not "github.com" in raw_url and not SITE_URL.replace("https://", "").replace("http://", "") in raw_url:
                url_context = fetch_url_context(raw_url)

        if is_update and current_topic:
            user_prompt = f"""
[기존 포스팅 기획안]
{json.dumps(current_topic, ensure_ascii=False, indent=2)}

[사용자의 추가 첨언 및 신규 자료]
{user_input}
{url_context}

[전체 요청 히스토리]
{chr(10).join([f"- {fb}" for fb in feedbacks])}

기존 기획안에 사용자의 추가 첨언 및 요구사항을 정밀하게 반영하여 한층 더 완성도 높은 기획안으로 업데이트해주세요.
- 사용자가 여러 개의 글(시리즈/챕터별) 작성을 요청하는 경우: JSON 리스트 [ {{ ... }}, {{ ... }} ] 형식
- 단일 글인 경우: 단일 JSON 객체 {{ ... }} 형식
반드시 마크다운(```json) 없이 순수 JSON 형식으로만 응답하세요.
"""
        else:
            user_prompt = f"""
다음 사용자의 입력 자료나 요청을 바탕으로 전문 블로그 포스팅 기획안을 작성해주세요.

[사용자 입력/요청]
{user_input}
{url_context}

[출력 형식 및 작성 가이드]
1. 사용자가 '여러 개', '시리즈', '각 챕터별', 'n개' 등 복수 포스팅을 요구하거나, 링크된 자료에 여러 챕터/주제가 있어 각 주제별 1개씩 복수 글 작성을 요구하는 경우:
   반드시 각 글의 기획안을 포함하는 **JSON 리스트** 형식으로 응답하세요:
   [
     {{
       "title": "구체적인 독자 질문에 답하는 제목 1",
       "category": "등록 카테고리 중 주제에 맞는 값",
       "target_keyword": "핵심 키워드",
       "tags": ["태그1", "태그2", "태그3"],
       "key_points": ["다룰 핵심 내용1", "핵심 내용2", "핵심 내용3"]
     }},
     {{
       "title": "매력적인 제목 2",
       "category": "등록 카테고리 중 주제에 맞는 값",
       "target_keyword": "핵심 키워드",
       "tags": ["태그1", "태그2"],
       "key_points": ["다룰 핵심 내용1", "핵심 내용2"]
     }}
   ]

2. 단일 글 작성 요청인 경우:
   단일 JSON 객체 형식으로 응답하세요:
   {{
     "title": "구체적인 독자 질문에 답하는 제목",
     "category": "등록 카테고리 중 주제에 맞는 값",
     "target_keyword": "핵심 롱테일 키워드",
     "tags": ["태그1", "태그2", "태그3", "태그4"],
     "key_points": ["핵심 포인트1", "포인트2", "포인트3"]
   }}

반드시 마크다운 코드블록(```json) 없이 순수한 JSON으로만 응답하세요.
"""
        raw_output = runner.generate_text(system_prompt=system_prompt + "\n" + EDITORIAL_RULES, user_prompt=user_prompt)
        if not raw_output:
            raise Exception("Antigravity 파이프라인에서 응답을 생성하지 못했습니다.")

        topic_data = extract_json(raw_output)

        # 1. 다중 글(시리즈/챕터별) 기획안 처리
        if isinstance(topic_data, list):
            session["topics"] = topic_data
            session["topic"] = topic_data[0] if topic_data else {}
            session["is_multi"] = True
            session["state"] = "PLANNING_MULTI"
            sessions[chat_id] = session

            topics_count = len(topic_data)
            header_title = f"📚 <b>[다중 포스팅 기획안 - 총 {topics_count}편]</b>"
            topics_list_str = "\n\n".join([
                f"<b>{idx+1}. {t.get('title')}</b>\n"
                f"   🏷️ {t.get('category')} | 🎯 #{t.get('target_keyword')}\n"
                f"   🏷️ 태그: #{', #'.join(t.get('tags', []))}\n"
                f"   📝 핵심: {', '.join(t.get('key_points', [])[:2])}"
                for idx, t in enumerate(topic_data)
            ])

            reply_text = (
                f"{header_title}\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"{topics_list_str}\n\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"💡 <i>요청하신 자료/챕터별로 총 {topics_count}편의 글이 연속 기획되었습니다.</i>\n"
                f"아래 버튼을 누르면 1편부터 {topics_count}편까지 <b>자동으로 고품질 작성 및 순차 배포</b>를 진행합니다."
            )

            keyboard = [
                [InlineKeyboardButton(f"🚀 {topics_count}편 일괄 순차 발행 & 배포", callback_data="btn_batch_publish")],
                [InlineKeyboardButton("❌ 취소 및 초기화", callback_data="btn_cancel_session")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await processing_msg.edit_text(reply_text, reply_markup=reply_markup, parse_mode="HTML")
            return

        # 2. 단일 글 기획안 처리
        session["topic"] = topic_data
        session["is_multi"] = False
        session["state"] = "PLANNING"
        sessions[chat_id] = session

        header_title = "🔄 <b>[포스팅 기획안 업데이트 완료]</b>" if is_update else "🎯 <b>[포스팅 기획안]</b>"
        points_str = "\n".join([f"  • {kp}" for kp in topic_data.get("key_points", [])])
        reply_text = (
            f"{header_title}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📌 <b>제목</b>: <b>{topic_data.get('title')}</b>\n"
            f"🏷️ <b>카테고리</b>: {topic_data.get('category')} | 🎯 <b>키워드</b>: #{topic_data.get('target_keyword')}\n"
            f"🏷️ <b>태그</b>: #{', #'.join(topic_data.get('tags', []))}\n\n"
            f"📝 <b>다룰 핵심 내용</b>:\n{points_str}\n\n"
            f"💡 <i>추가 첨언이나 자료가 있다면 메시지로 계속 보내주세요. 기획안에 즉시 반영됩니다.</i>"
        )

        keyboard = [
            [
                InlineKeyboardButton("✍️ 본문 초안 작성 (검토)", callback_data="btn_create_draft"),
                InlineKeyboardButton("✍️ 초안 작성 후 검토", callback_data="btn_quick_publish")
            ],
            [InlineKeyboardButton("❌ 취소 및 초기화", callback_data="btn_cancel_session")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await processing_msg.edit_text(reply_text, reply_markup=reply_markup, parse_mode="HTML")

    except Exception as e:
        logger.error(f"Error in generate_or_update_topic_plan: {e}")
        await processing_msg.edit_text(f"❌ 기획안 처리 중 오류가 발생했습니다: {e}")
    finally:
        if chat_id in sessions:
            sessions[chat_id]["busy"] = False

# -------------------------------------------------------------
# STEP 2: ARTICLE DRAFTING & ITERATIVE REFINEMENT
# -------------------------------------------------------------
async def create_article_draft(chat_id, message_id, context):
    session = sessions.get(chat_id)
    if not session or not session.get("topic"):
        await context.bot.send_message(chat_id=chat_id, text="⚠️ 기획안 세션이 없습니다. 새 주제를 입력해주세요.")
        return

    invalidate_approvals(session)
    session["busy"] = True
    topic_data = session["topic"]
    feedbacks = session.get("feedbacks", [])

    status_msg = await context.bot.send_message(
        chat_id=chat_id,
        text="✍️ <b>Antigravity 에이전트가 주제별 아티클 초안을 작성 중입니다... (약 1~2분 소요)</b>",
        parse_mode="HTML"
    )

    session["busy"] = True
    session["action"] = "주제별 본문 초안 작성 (Antigravity CLI)"
    session["started_at"] = time.time()
    sessions[chat_id] = session

    try:
        writer = ContentWriter(config)
        
        # If there are additional user feedbacks, append them to key_points
        enhanced_topic = dict(topic_data)
        if len(feedbacks) > 1:
            enhanced_topic["key_points"] = enhanced_topic.get("key_points", []) + [
                f"[사용자 추가 요청] {fb}" for fb in feedbacks[1:]
            ]

        article = writer.write_article(enhanced_topic)
        session["draft"] = article
        approval_token = issue_approval(session, "draft")
        session["state"] = "DRAFTED"
        sessions[chat_id] = session

        inspector = PolicyInspector(config)
        inspection = inspector.inspect_article(article)

        char_count = inspection.get("char_count", len(article.get("markdown_content", "")))
        score = inspection.get("score", 90)
        faqs_count = len(article.get("faqs", []))
        
        # Excerpt preview
        content_preview = article.get("markdown_content", "").replace("#", "").strip()[:200]

        reply_text = (
            f"📄 <b>[본문 초안 작성 완료]</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📌 <b>제목</b>: <b>{article.get('title')}</b>\n"
            f"📊 <b>형식 점검 참고값</b>: <code>{score}/100점</code> | 📏 <b>분량</b>: <code>{char_count:,}자</code>\n"
            f"⏱️ <b>소요 시간</b>: {article.get('readingTime', '6 min read')} | ❓ <b>FAQ</b>: {faqs_count}개\n\n"
            f"📖 <b>서론 미리보기</b>:\n"
            f"<i>\"{content_preview}...\"</i>\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"💡 <b>수정/첨언 방법</b>:\n"
            f"• 본문에 추가하고 싶은 내용, 수정할 점, 변경할 제목 등을 <b>메시지로 편하게 보내주시면 초안에 즉시 반영</b>됩니다!\n"
            f"• 내용이 마음에 드시면 아래 <b>[🚀 최종 발행 및 배포]</b> 버튼을 눌러주세요."
        )

        keyboard = [
            [InlineKeyboardButton("🚀 최종 발행 및 배포", callback_data=f"btn_publish_draft:{approval_token}")],
            [
                InlineKeyboardButton("✏️ 추가 수정 (피드백)", callback_data="btn_request_more_draft_edit"),
                InlineKeyboardButton("📖 초안 전문 보기", callback_data="btn_view_full_draft")
            ],
            [InlineKeyboardButton("❌ 취소 및 초기화", callback_data="btn_cancel_session")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await status_msg.edit_text(reply_text, reply_markup=reply_markup, parse_mode="HTML")

    except Exception as e:
        logger.error(f"Error in create_article_draft: {e}")
        await status_msg.edit_text(f"❌ 본문 초안 작성 중 오류가 발생했습니다: {e}")
    finally:
        if chat_id in sessions:
            sessions[chat_id]["busy"] = False

async def refine_article_draft(message, chat_id, user_feedback, context):
    session = sessions.get(chat_id)
    if not session or not session.get("draft"):
        await message.reply_text("⚠️ 검토 중인 초안이 없습니다. 새 주제를 입력해주세요.")
        return

    invalidate_approvals(session)
    session["busy"] = True
    processing_msg = await message.reply_text("🔄 보내주신 피드백/자료를 반영하여 본문 초안을 수정 및 보강 중입니다...")

    current_draft = session["draft"]
    session["busy"] = True
    session["action"] = "본문 피드백/첨언 반영 및 수정 중 (Antigravity CLI)"
    session["started_at"] = time.time()
    sessions[chat_id] = session

    try:
        runner = AntigravityRunner(config)
        system_prompt = "당신은 해당 블로그 주제에 맞는 편집 보조입니다. 기존 초안에 사용자의 수정 요청 및 추가 자료를 완벽히 반영하여 업그레이드하고, 반드시 유효한 JSON 형식으로만 응답하세요."

        user_prompt = f"""
[현재 작성된 초안 데이터]
- 제목: {current_draft.get('title')}
- 메타 설명: {current_draft.get('description')}
- 카테고리: {current_draft.get('category')}
- 태그: {', '.join(current_draft.get('tags', []))}
- FAQ 목록: {json.dumps(current_draft.get('faqs', []), ensure_ascii=False)}
- 본문 마크다운:
{current_draft.get('markdown_content')}

[사용자의 추가 피드백 및 신규 첨언/자료]
{user_feedback}

위 사용자 피드백을 본문 전체에 자연스럽고 깊이 있게 녹여내어 글을 수정해주세요.
(H2/H3 구조, 비교 표, 실전 팁, FAQ 모두 충실하게 보강)
반드시 마크다운 없이 순수 JSON 형식으로 응답하세요.

출력 JSON 형식:
{{
  "title": "수정/보강된 제목",
  "description": "수정된 메타 디스크립션",
  "category": "{current_draft.get('category')}",
  "tags": ["태그1", "태그2", "태그3"],
  "readingTime": "7 min read",
  "faqs": [
    {{"question": "질문1", "answer": "답변1"}},
    {{"question": "질문2", "answer": "답변2"}},
    {{"question": "질문3", "answer": "답변3"}}
  ],
  "change_summary": "수정 및 보강된 핵심 내용 요약 (1~2줄)",
  "markdown_content": "수정된 본문 전체 내용 (마크다운 H2, H3, 표, 리스트 포함)"
}}
"""
        raw_output = runner.generate_text(system_prompt=system_prompt + "\n" + EDITORIAL_RULES, user_prompt=user_prompt)
        if not raw_output:
            raise Exception("Antigravity 에디터로부터 응답을 받지 못했습니다.")

        updated_draft = extract_json(raw_output)
        session["draft"] = updated_draft
        approval_token = issue_approval(session, "draft")
        sessions[chat_id] = session

        inspector = PolicyInspector(config)
        inspection = inspector.inspect_article(updated_draft)
        char_count = inspection.get("char_count", len(updated_draft.get("markdown_content", "")))

        reply_text = (
            f"🔄 <b>[초안 수정 및 보강 완료]</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📌 <b>제목</b>: <b>{updated_draft.get('title')}</b>\n"
            f"💡 <b>반영 사항</b>: {updated_draft.get('change_summary', '피드백 반영 완료')}\n"
            f"📏 <b>수정 후 분량</b>: <code>{char_count:,}자</code> | ⏱️ {updated_draft.get('readingTime')}\n\n"
            f"💡 <i>추가 수정사항이 더 있으시면 메시지를 보내주세요. 마음에 드시면 즉시 발행할 수 있습니다.</i>"
        )

        keyboard = [
            [InlineKeyboardButton("🚀 최종 발행 및 배포", callback_data=f"btn_publish_draft:{approval_token}")],
            [
                InlineKeyboardButton("✏️ 추가 수정 (피드백)", callback_data="btn_request_more_draft_edit"),
                InlineKeyboardButton("📖 수정된 전문 보기", callback_data="btn_view_full_draft")
            ],
            [InlineKeyboardButton("❌ 취소 및 초기화", callback_data="btn_cancel_session")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await processing_msg.edit_text(reply_text, reply_markup=reply_markup, parse_mode="HTML")

    except Exception as e:
        logger.error(f"Error in refine_article_draft: {e}")
        await processing_msg.edit_text(f"❌ 초안 수정 중 오류가 발생했습니다: {e}")
    finally:
        if chat_id in sessions:
            sessions[chat_id]["busy"] = False

# -------------------------------------------------------------
# STEP 2-1: QUEUE DRAFT DIRECT EDITING & HITL REFINEMENT
# -------------------------------------------------------------
async def start_queue_draft_edit(reply_target, chat_id, draft_id, context):
    queue = DraftApprovalQueue()
    draft = queue.get_draft(draft_id)

    if not draft:
        msg = f"⚠️ 초안(<code>{draft_id}</code>)을 대기 큐에서 찾을 수 없습니다."
        if hasattr(reply_target, "edit_message_text"):
            await reply_target.edit_message_text(msg, parse_mode="HTML")
        else:
            await reply_target.reply_text(msg, parse_mode="HTML")
        return

    article = draft.get("article", {})
    title = article.get("title", draft.get("title", "제목 없음"))
    review = draft.get("review", {})
    points = draft.get("human_edit_points") or review.get("human_edit_points") or []
    if not points:
        body = article.get("markdown_content", "")
        markers = re.findall(r"(\[(?:💡|🔍)[^\]\n]+\])", body)
        points = [{"index": i, "marker": m, "recommendation": "수정/확인 필요"} for i, m in enumerate(markers, 1)]

    sessions[chat_id] = {
        "state": "QUEUE_DRAFT_EDITING",
        "draft_id": draft_id,
        "draft": article,
        "topic": draft.get("topic", {}),
        "review": review,
        "human_edit_points": points,
        "feedbacks": [],
        "busy": False
    }

    from html import escape
    p_lines = []
    if points:
        for p in points:
            idx = p.get("index", len(p_lines) + 1)
            m = p.get("marker", "")
            rec = p.get("recommendation") or p.get("guide") or ""
            p_lines.append(f"  {idx}️⃣ <b>{escape(str(m))}</b>\n     ↳ <i>{escape(str(rec))}</i>")
        points_info = "💡 <b>[본문 수정 추천 위치 (경험/수치 확인)]</b>:\n" + "\n".join(p_lines) + "\n\n"
    else:
        points_info = "💡 <i>본문에 특별한 마커는 없으나, 실제 경험담 추가나 전체적인 내용 보강이 가능합니다.</i>\n\n"

    guide_msg = (
        f"✏️ <b>[K-Pop 한글 초안 직접 수정 모드 - {escape(title[:30])}]</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🆔 <b>초안 ID</b>: <code>{escape(draft_id)}</code>\n\n"
        f"{points_info}"
        f"💬 <b>수정 안내</b>:\n"
        f"가사 해설, 문법 포인트, 발음 가이드 등 보완하고 싶은 내용을 메시지로 보내주세요.\n\n"
        f"예시:\n"
        f"• <code>후렴구 가사 번역과 연음(batchim) 발음 가이드를 더 알기 쉽게 풀어줘</code>\n"
        f"• <code>문법 설명 섹션에 실생활에서 바로 쓸 수 있는 대화 예문 2개 더 추가해줘</code>\n\n"
        f"보내주신 피드백을 AI가 본문에 자연스럽게 녹여내어 즉시 큐를 갱신합니다."
    )

    keyboard = [
        [InlineKeyboardButton("📖 현재 초안 전문 보기", callback_data=f"view_draft:{draft_id}")],
        [InlineKeyboardButton("❌ 수정 모드 취소", callback_data="btn_cancel_session")]
    ]
    await context.bot.send_message(chat_id=chat_id, text=guide_msg, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))

async def refine_queued_draft(message, chat_id, user_feedback, context):
    session = sessions.get(chat_id)
    if not session or not session.get("draft") or not session.get("draft_id"):
        await message.reply_text("⚠️ 수정 대상 초안이 없습니다. 다시 선택해주세요.")
        return

    session["busy"] = True
    draft_id = session["draft_id"]
    current_draft = session["draft"]

    processing_msg = await message.reply_text(f"🔄 보내주신 피드백을 K-Pop 초안(<code>{draft_id[:16]}...</code>)에 반영하여 수정 중입니다...", parse_mode="HTML")

    try:
        runner = AntigravityRunner(config)
        system_prompt = (
            "당신은 글로벌 K-Pop 팬들을 위한 한국어 교육 콘텐츠(가사 분석, 문법, 어휘, 발음)의 최고 편집자입니다. "
            "사용자가 제공한 수정 요청사항이나 피드백을 기존 초안에 자연스럽고 깊이 있게 녹여내어 교육적 완성도를 대폭 업그레이드하세요.\n"
            "- 정확한 한글 맞춤법, 국어의 로마자 표기법(Revised Romanization), 자연스러운 영어 번역 유지.\n"
            "- 문법 공식(Grammar Formula)과 일상 회화 예문(Conversational Examples) 보강.\n"
            "- 반드시 유효한 순수 JSON 형식으로만 응답하세요."
        )

        user_prompt = f"""
[현재 초안 데이터]
- 제목: {current_draft.get('title')}
- 메타 설명: {current_draft.get('description')}
- 카테고리: {current_draft.get('category')}
- 태그: {', '.join(current_draft.get('tags', []))}
- FAQ 목록: {json.dumps(current_draft.get('faqs', []), ensure_ascii=False)}
- 본문 마크다운:
{current_draft.get('markdown_content')}

[사용자가 직접 입력한 수정 피드백]
{user_feedback}

위 사용자의 피드백을 본문 문맥에 완벽히 반영하여 한층 더 풍부하고 명확한 K-Pop 한국어 학습 레슨으로 업그레이드하세요.

출력 JSON 형식:
{{
  "title": "수정/보강된 제목",
  "description": "수정된 메타 디스크립션",
  "category": "{current_draft.get('category')}",
  "tags": {json.dumps(current_draft.get('tags', []), ensure_ascii=False)},
  "readingTime": "6 min read",
  "faqs": {json.dumps(current_draft.get('faqs', []), ensure_ascii=False)},
  "change_summary": "수정 및 피드백 반영 핵심 내용 요약 (1~2줄)",
  "markdown_content": "수정된 본문 전체 내용 (마크다운 H2, H3, 표, 리스트 포함)"
}}
"""
        raw_output = runner.generate_text(system_prompt=system_prompt + "\n" + EDITORIAL_RULES, user_prompt=user_prompt)
        if not raw_output:
            raise Exception("AI 엔진으로부터 수정 응답을 받지 못했습니다.")

        updated_draft = extract_json(raw_output)

        # 큐 업데이트!
        change_summary = updated_draft.get("change_summary", "사용자 직접 수정 및 피드백 반영")
        queue = DraftApprovalQueue()
        queue.update_draft_content(draft_id, updated_draft, change_summary=change_summary)

        session["draft"] = updated_draft
        sessions[chat_id] = session

        inspector = PolicyInspector(config)
        inspection = inspector.inspect_article(updated_draft)
        char_count = inspection.get("char_count", len(updated_draft.get("markdown_content", "")))

        from html import escape
        reply_text = (
            f"🔄 <b>[K-Pop 한글 초안 직접 수정 및 큐 반영 완료]</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📌 <b>제목</b>: <b>{escape(updated_draft.get('title', ''))}</b>\n"
            f"🆔 <b>초안 ID</b>: <code>{escape(draft_id)}</code>\n"
            f"💡 <b>수정 내용</b>: {escape(change_summary)}\n"
            f"📏 <b>본문 분량</b>: <code>{char_count:,}자</code>\n\n"
            f"✨ <i>대기 큐가 성공적으로 갱신되었습니다. 아래 버튼을 눌러 즉시 발행하거나 추가 수정을 진행하세요.</i>"
        )

        keyboard = [
            [InlineKeyboardButton("🚀 수정본 즉시 승인 및 발행", callback_data=f"approve:{draft_id}")],
            [
                InlineKeyboardButton("✏️ 추가 수정하기", callback_data=f"edit_draft:{draft_id}"),
                InlineKeyboardButton("📖 수정본 전문 보기", callback_data=f"view_draft:{draft_id}")
            ],
            [InlineKeyboardButton("❌ 수정 모드 종료", callback_data="btn_cancel_session")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await processing_msg.edit_text(reply_text, reply_markup=reply_markup, parse_mode="HTML")

    except Exception as e:
        logger.error(f"Error in refine_queued_draft: {e}")
        await processing_msg.edit_text(f"❌ 초안 수정 중 오류가 발생했습니다: {e}")
    finally:
        if chat_id in sessions:
            sessions[chat_id]["busy"] = False

# -------------------------------------------------------------
# STEP 3: PUBLISHING TO GITHUB PAGES
# -------------------------------------------------------------
async def execute_publish(chat_id, context, is_draft=True, approval=None):
    session = sessions.get(chat_id)
    if not session:
        await context.bot.send_message(chat_id=chat_id, text="⚠️ 발행할 작업 세션을 찾을 수 없습니다.")
        return

    # An approval of a plan is not approval of a not-yet-written article.
    if not is_draft or not session.get("draft"):
        await create_article_draft(chat_id, None, context)
        return

    if not approval or approval.get("session") is not session:
        await context.bot.send_message(chat_id=chat_id, text="초안 버전이 바뀌었습니다. 최신 본문에 표시된 승인 버튼을 사용하세요.")
        return

    status_msg = await context.bot.send_message(
        chat_id=chat_id,
        text="🚀 <b>승인한 초안 버전을 저장소에 반영하는 중입니다...</b>",
        parse_mode="HTML"
    )

    try:
        writer = ContentWriter(config)
        publisher = GitHubPublisher(config)
        inspector = PolicyInspector(config)
        telegram = TelegramNotifier(config)
        indexer = GoogleIndexing(config)

        article = approval["article"]

        inspection = inspector.inspect_article(article)
        saved_path = publisher.publish_article(article, human_approved=True)
        
        site_url = SITE_URL
        post_slug = os.path.splitext(os.path.basename(saved_path))[0]
        full_post_url = f"{site_url.rstrip('/')}/blog/{post_slug}/"

        indexer.ping_sitemap()
        telegram.send_article_published(article, inspection, full_post_url)

        # Clear session
        if sessions.get(chat_id) is session:
            del sessions[chat_id]

        msg = f"""🎉 <b>[저장소 반영 요청 완료]</b>
━━━━━━━━━━━━━━━━━━━━
📌 <b>제목</b>: <b>{article.get('title')}</b>
🏷️ <b>카테고리</b>: {article.get('category')}
📊 <b>형식 점검 참고값</b>: {inspection.get('score', 90)}점 ({inspection.get('char_count', 1500):,}자)

🔗 <b>글 바로가기</b>:
<a href="{full_post_url}">{full_post_url}</a>

✨ <i>저장소 커밋/Push 요청이 완료되었습니다. Pages 배포 결과와 공개 URL 반영은 별도로 확인하세요.</i>"""

        reply_markup = {
            "inline_keyboard": [
                [{"text": "🌐 게시글 확인하기", "url": full_post_url}]
            ]
        }
        await status_msg.edit_text(msg, parse_mode="HTML", reply_markup=reply_markup, disable_web_page_preview=False)

    except Exception as e:
        logger.error(f"Error in execute_publish: {e}")
        await status_msg.edit_text(f"❌ 배포 중 오류가 발생했습니다: {e}")
    finally:
        session["busy"] = False
        session.pop("publication_inflight", None)

async def execute_batch_publish(chat_id, context):
    session = sessions.get(chat_id)
    if not session or not session.get("topics"):
        await context.bot.send_message(chat_id=chat_id, text="검토할 기획안이 없습니다.")
        return
    session["busy"] = True
    completed = []
    try:
        writer = ContentWriter(config)
        reviewer = EditorialReviewAgent(config)
        queue = DraftApprovalQueue()
        telegram = TelegramNotifier(config)
        for topic in session["topics"]:
            article = writer.write_article(topic)
            review = reviewer.review_article(article, topic)
            draft_id = queue.add_draft(article, review, topic=topic)
            completed.append(draft_id)
            telegram.send_review_report(draft_id, article, review)
        await context.bot.send_message(chat_id=chat_id, text=f"{len(completed)}편을 검토 큐에 저장했습니다. 각 초안의 본문과 출처를 확인한 뒤 승인하세요.")
    except Exception as exc:
        await context.bot.send_message(chat_id=chat_id, text=f"초안 생성 중단. 저장된 초안 {len(completed)}편은 검토 큐에 남아 있습니다: {exc}")
    finally:
        session["busy"] = False

# -------------------------------------------------------------
# STEP 4: EXISTING BLOG POST EDITING
# -------------------------------------------------------------
async def process_edit_input(message, user_text, blog_url_match, context, is_update=False):
    if message.chat_id in sessions:
        invalidate_approvals(sessions[message.chat_id])
    loading_text = "🔄 추가 수정 요청사항을 반영 중입니다..." if is_update else "🔍 수정할 블로그 포스팅을 조회하고 수정안을 기획 중입니다. (Antigravity CLI 가동 중...)"
    processing_msg = await message.reply_text(loading_text)
    
    chat_id = message.chat_id
    session = sessions.get(chat_id, {})

    slug = session.get("slug")
    if not slug and blog_url_match:
        slug = blog_url_match.group(1).rstrip("/")
    elif not slug:
        parts = user_text.split()
        for p in parts:
            if "blog/" in p:
                slug = p.split("blog/")[-1].strip("/")
                break

    if not slug:
        await processing_msg.edit_text("❌ 수정할 글의 슬러그(URL)를 찾을 수 없습니다. 블로그 링크를 정확히 입력해주세요.")
        return

    filepath = os.path.join(CONTENT_DIR, f"{slug}.md")
    if not os.path.exists(filepath):
        matched = [f for f in os.listdir(CONTENT_DIR) if f.startswith(slug) and f.endswith(".md")]
        if matched:
            filepath = os.path.join(CONTENT_DIR, matched[0])
            slug = os.path.splitext(matched[0])[0]
        else:
            await processing_msg.edit_text(f"❌ 해당 포스팅 파일(`{slug}.md`)을 블로그 저장소에서 찾을 수 없습니다.")
            return

    session["busy"] = True
    session["action"] = f"기존 글({slug}) 수정안 기획 (Antigravity CLI)"
    session["started_at"] = time.time()
    sessions[chat_id] = session

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            original_raw = f.read()

        runner = AntigravityRunner(config)
        system_prompt = "당신은 전문 기술 블로그 에디터입니다. 기존 글을 사용자의 요청에 맞추어 보강 및 수정하고, 반드시 유효한 JSON 형식으로만 응답해야 합니다."
        
        feedbacks = session.get("feedbacks", [user_text])
        if is_update and session.get("data"):
            prev_data = session["data"]
            base_content = prev_data.get("markdown_content", original_raw)
            base_title = prev_data.get("title", "")
            base_slug = prev_data.get("new_slug", slug)
            prompt_context = f"""[직전 수정본 내용]
- 현재 제목: {base_title}
- 현재 URL 슬러그: {base_slug}
- 현재 메타 설명: {prev_data.get('description', '')}
- 현재 FAQ: {json.dumps(prev_data.get('faqs', []), ensure_ascii=False)}
- 현재 본문 마크다운:
{base_content}"""
        else:
            prompt_context = f"[기존 원본 포스팅 내용]\n{original_raw}"

        user_prompt = f"""
{prompt_context}

[사용자의 추가 수정 요청사항]
{user_text}

[전체 요청 히스토리]
{chr(10).join([f"- {fb}" for fb in feedbacks])}

위 사용자 요청사항을 반영하여 글을 전면 수정/보강해주세요.
프론트매터 메타데이터(title, description, category, tags, faqs 등)와 본문(markdown_content)을 충실하게 작성하고,
무엇이 변경되었는지 핵심 요약(change_summary)을 포함하여 오직 유효한 JSON 형식으로 응답하세요.

출력 JSON 형식:
{{
  "title": "수정된 매력적인 제목",
  "new_slug": "사용자가 URL/슬러그 변경을 요청했거나, 제목에 맞게 영문 슬러그를 변경해야 할 경우에만 새로운 슬러그 지정 (예: 2026-08-31-qwen-38-27b-review). 변경이 불필요하면 기존 슬러그 그대로 유지",
  "description": "수정된 메타 디스크립션",
  "category": "카테고리",
  "tags": ["태그1", "태그2", "태그3"],
  "readingTime": "8 min read",
  "faqs": [
    {{"question": "질문1", "answer": "답변1"}},
    {{"question": "질문2", "answer": "답변2"}},
    {{"question": "질문3", "answer": "답변3"}}
  ],
  "change_summary": "수정된 핵심 사항 요약 (1~3줄)",
  "markdown_content": "수정된 본문 전체 내용 (마크다운 H2, H3, 표, 리스트 포함)"
}}
"""
        raw_output = runner.generate_text(system_prompt=system_prompt + "\n" + EDITORIAL_RULES, user_prompt=user_prompt)
        if not raw_output:
            raise Exception("Antigravity 에디터로부터 응답을 받지 못했습니다.")

        modified_data = extract_json(raw_output)
        session["slug"] = slug
        session["data"] = modified_data
        approval_token = issue_approval(session, "data")
        session["filepath"] = filepath
        session["state"] = "EDITING"
        sessions[chat_id] = session

        new_slug_info = ""
        new_slug = modified_data.get("new_slug")
        if new_slug and new_slug != slug:
            new_slug_info = f"\n🔗 <b>URL 변경</b>: <code>{slug}</code> ➔ <code>{new_slug}</code>"

        header_title = "🔄 <b>[추가 수정안 업데이트 완료]</b>" if is_update else "✏️ <b>[기존 포스팅 수정 기획안]</b>"
        char_count = len(modified_data.get("markdown_content", "").replace(" ", "").replace("\n", ""))

        reply_text = (
            f"{header_title}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📌 <b>대상 슬러그</b>: <code>{slug}</code>{new_slug_info}\n"
            f"📝 <b>수정된 제목</b>: <b>{modified_data.get('title')}</b>\n"
            f"📏 <b>본문 분량</b>: <code>{char_count:,}자</code> | ⏱️ {modified_data.get('readingTime', '7 min read')}\n"
            f"🏷️ <b>태그</b>: #{', #'.join(modified_data.get('tags', []))}\n\n"
            f"💡 <b>주요 변경 사항</b>:\n"
            f"{modified_data.get('change_summary', '본문 및 구조 보강')}\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"💡 <b>진행 방법</b>:\n"
            f"• 추가로 수정하거나 덧붙이고 싶은 내용이 있다면 <b>메시지로 편하게 계속 보내주세요. 실시간으로 수정안이 업데이트</b>됩니다.\n"
            f"• 수정 내용이 마음에 드시면 아래 <b>[✅ 수정 및 재배포]</b> 버튼을 눌러주세요."
        )

        keyboard = [
            [InlineKeyboardButton("🚀 최종 수정 및 재배포", callback_data=f"btn_apply_edit:{approval_token}")],
            [
                InlineKeyboardButton("✏️ 추가 수정 (피드백)", callback_data="btn_request_more_edit"),
                InlineKeyboardButton("📖 수정본 전문 보기", callback_data="btn_view_full_edit")
            ],
            [InlineKeyboardButton("❌ 취소 및 초기화", callback_data="btn_cancel_session")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await processing_msg.edit_text(reply_text, reply_markup=reply_markup, parse_mode="HTML")

    except Exception as e:
        logger.error(f"Error in process_edit_input: {e}")
        await processing_msg.edit_text(f"❌ 수정 기획안 작성 중 오류가 발생했습니다: {e}")
    finally:
        if chat_id in sessions:
            sessions[chat_id]["busy"] = False

async def execute_edit_publish(chat_id, context, approval=None):
    session = sessions.get(chat_id)
    if not session or not session.get("data"):
        await context.bot.send_message(chat_id=chat_id, text="⚠️ 수정할 작업 세션이 없습니다.")
        return

    if not approval or approval.get("session") is not session:
        await context.bot.send_message(chat_id=chat_id, text="수정안 버전이 바뀌었습니다. 최신 수정안의 승인 버튼을 사용하세요.")
        return

    status_msg = await context.bot.send_message(
        chat_id=chat_id,
        text="✍️ <b>수정된 내용을 저장하고 GitHub Pages에 재배포 중입니다...</b>",
        parse_mode="HTML"
    )

    try:
        slug = approval["slug"]
        article_data = approval["article"]
        new_slug = article_data.get("new_slug")
        publisher = GitHubPublisher(config)
        indexer = GoogleIndexing(config)
        
        saved_path, final_slug = publisher.update_existing_article(slug, article_data, new_slug=new_slug, human_approved=True)
        site_url = SITE_URL
        full_post_url = f"{site_url.rstrip('/')}/blog/{final_slug}/"
        
        indexer.ping_sitemap()
        
        if sessions.get(chat_id) is session:
            del sessions[chat_id]

        slug_changed_note = f"\n🔗 <b>새 URL</b>: <a href=\"{full_post_url}\">{full_post_url}</a>\n" if final_slug != slug else ""

        msg = f"""🎉 <b>[포스팅 수정 및 저장소 반영 요청 완료]</b>
━━━━━━━━━━━━━━━━━━━━
📌 <b>제목</b>: <b>{article_data.get('title')}</b>
💡 <b>수정 사항</b>: {article_data.get('change_summary', '수정 완료')}{slug_changed_note}
🔗 <b>글 바로가기</b>:
<a href="{full_post_url}">{full_post_url}</a>

✨ <i>저장소 반영 요청이 완료되었습니다. Pages 결과와 공개 URL은 별도로 확인하세요.</i>"""

        reply_markup = {
            "inline_keyboard": [
                [{"text": "🌐 수정된 글 확인하기", "url": full_post_url}]
            ]
        }
        await status_msg.edit_text(msg, parse_mode="HTML", reply_markup=reply_markup, disable_web_page_preview=False)

    except Exception as e:
        logger.error(f"Error in execute_edit_publish: {e}")
        await status_msg.edit_text(f"❌ 수정 배포 중 오류가 발생했습니다: {e}")
    finally:
        session["busy"] = False
        session.pop("publication_inflight", None)

# -------------------------------------------------------------
# BUTTON CALLBACK HANDLER
# -------------------------------------------------------------
@require_allowed_chat
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    try:
        await query.answer()
    except Exception as e:
        logger.warning(f"Failed to answer callback query: {e}")
    data = query.data
    chat_id = query.message.chat_id

    if data == "btn_cancel_session":
        if chat_id in sessions:
            del sessions[chat_id]
        await query.edit_message_text("❌ 작업 세션이 취소되었습니다.")
        return

    # HITL 대기 큐 버튼 콜백
    if data.startswith("approve:"):
        target_id = data.split("approve:", 1)[1]
        await query.edit_message_text("🚀 <b>[초안 승인 접수]</b> GitHub Pages 배포를 시작합니다...", parse_mode="HTML")
        success, res = publish_queued_draft(config, target_id, human_approved=True)
        if success:
            await query.message.reply_text(
                f"🎉 <b>[포스팅 승인 및 저장소 반영 요청 완료]</b>\n━━━━━━━━━━━━━━━━━━━━\n"
                f"🔗 <b>글 바로가기</b>: <a href=\"{res}\">{res}</a>\n\n"
                f"✨ <i>저장소 반영 요청이 완료되었습니다. Pages 배포 결과와 실제 URL을 확인하세요.</i>",
                parse_mode="HTML",
                disable_web_page_preview=False
            )
        else:
            await query.message.reply_text(f"❌ 배포 실패: {res}")
        return

    if data.startswith("reject:"):
        target_id = data.split("reject:", 1)[1]
        queue = DraftApprovalQueue()
        queue.mark_rejected(target_id)
        await query.edit_message_text(f"❌ 초안(<code>{target_id[:16]}...</code>)이 발행 보류 처리되었습니다.", parse_mode="HTML")
        return

    if data.startswith("edit_draft:"):
        target_id = data.split("edit_draft:", 1)[1].strip()
        await start_queue_draft_edit(query, chat_id, target_id, context)
        return

    if data.startswith("view_draft:"):
        target_id = data.split("view_draft:", 1)[1]
        queue = DraftApprovalQueue()
        draft = queue.get_draft(target_id)
        if draft:
            from html import escape
            raw_content = draft.get("article", {}).get("markdown_content", "본문 없음")
            # 본문 설명 이미지 figure 태그를 텔레그램 가독성 텍스트로 변환
            display_content = re.sub(
                r'<!-- article-illustration:[^>]+ -->[\s\S]*?<figcaption[^>]*>([\s\S]*?)</figcaption>[\s\S]*?<!-- /article-illustration:[^>]+ -->',
                r'\n🖼️ <i>[본문 설명 이미지: \1]</i>\n',
                raw_content
            )
            display_content = re.sub(r'<figure[^>]*>[\s\S]*?</figure>', '', display_content)
            display_content = re.sub(r'<img[^>]*>', '', display_content)
            if len(display_content) > 3500:
                display_content = display_content[:3500] + "\n\n... (분량 초과로 일부 생략되었습니다) ..."
            try:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"📖 <b>[본문 초안 전문 미리보기 - {escape(draft.get('title', ''))}]</b>\n\n{display_content}",
                    parse_mode="HTML"
                )
            except Exception:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"📖 [본문 초안 전문 미리보기 - {draft.get('title', '')}]\n\n{display_content}"
                )
        else:
            await context.bot.send_message(chat_id=chat_id, text="⚠️ 해당 초안을 찾을 수 없습니다.")
        return

    if data == "btn_create_draft":
        await query.edit_message_text("✍️ 초안 작성을 시작합니다...")
        asyncio.create_task(create_article_draft(chat_id, query.message.message_id, context))
        return

    if data == "btn_quick_publish":
        await query.edit_message_text("🚀 초안 작성 후 검토를 시작합니다...")
        asyncio.create_task(execute_publish(chat_id, context, is_draft=False))
        return

    if data == "btn_batch_publish":
        await query.edit_message_text("🚀 여러 초안을 생성하여 개별 검토 큐에 저장합니다...")
        asyncio.create_task(execute_batch_publish(chat_id, context))
        return

    if data == "btn_publish_draft" or data.startswith("btn_publish_draft:"):
        token = data.partition(":")[2]
        approval = consume_approval(sessions.get(chat_id), "draft", token)
        if approval is None:
            await query.edit_message_text("이 승인 버튼은 만료되었거나 이미 사용됐습니다. 최신 초안을 검토하세요.")
            return
        try:
            await execute_publish(chat_id, context, is_draft=True, approval=approval)
        finally:
            approval["session"]["busy"] = False
            approval["session"].pop("publication_inflight", None)
        return

    if data == "btn_apply_edit" or data.startswith("btn_apply_edit:"):
        token = data.partition(":")[2]
        approval = consume_approval(sessions.get(chat_id), "data", token)
        if approval is None:
            await query.edit_message_text("이 승인 버튼은 만료되었거나 이미 사용됐습니다. 최신 수정안을 검토하세요.")
            return
        try:
            await execute_edit_publish(chat_id, context, approval=approval)
        finally:
            approval["session"]["busy"] = False
            approval["session"].pop("publication_inflight", None)
        return

    if data == "btn_view_full_draft":
        session = sessions.get(chat_id)
        if session and session.get("draft"):
            content = session["draft"].get("markdown_content", "본문 없음")
            if len(content) > 3800:
                content = content[:3800] + "\n\n... (분량 초과로 일부 생략되었습니다) ..."
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"📖 [본문 초안 전문 미리보기]\n\n{content}"
            )
        else:
            await context.bot.send_message(chat_id=chat_id, text="⚠️ 현재 확인 가능한 초안이 없습니다.")
        return

    if data == "btn_request_more_edit":
        await context.bot.send_message(
            chat_id=chat_id,
            text="💬 <b>[추가 수정 모드]</b>\n"
                 "수정하고 싶은 점, 추가할 내용, 변경할 제목/URL 등을 <b>메시지로 편하게 보내주세요!</b>\n"
                 "<i>(예: \"결론에 로컬 구동 팁 추가\", \"벤치마크 표에 MMLU 점수 추가\", \"URL을 2026-08-31-qwen-review 로 변경\")</i>",
            parse_mode="HTML"
        )
        return

    if data == "btn_request_more_draft_edit":
        await context.bot.send_message(
            chat_id=chat_id,
            text="💬 <b>[초안 추가 수정 모드]</b>\n"
                 "초안에 추가/수정하고 싶은 내용을 <b>메시지로 편하게 보내주세요!</b>\n"
                 "<i>(예: \"소제목 말투를 더 친절하게 바꿔줘\", \"FAQ에 설치 방법 추가해줘\")</i>",
            parse_mode="HTML"
        )
        return

    if data.startswith("delete_confirm:"):
        slug = data.split("delete_confirm:", 1)[1]
        filepath = os.path.join(CONTENT_DIR, f"{slug}.md")
        if not os.path.exists(filepath):
            await query.edit_message_text(f"❌ 해당 게시글(<code>{slug}</code>)을 찾을 수 없습니다.", parse_mode="HTML")
            return
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
        title_match = re.search(r"^title:\s*(.+)$", content, re.MULTILINE)
        title = title_match.group(1).strip("'\"" ) if title_match else slug
        await query.edit_message_text(
            f"⚠️ <b>[글 삭제 최종 확인]</b>\n━━━━━━━━━━━━━━━━━━━━\n"
            f"📌 <b>제목</b>: <b>{title}</b>\n"
            f"🔗 <b>슬러그</b>: <code>{slug}</code>\n\n"
            f"⚠️ <i>이 작업은 되돌릴 수 없습니다.</i>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🗑️ 확인 - 영구 삭제", callback_data=f"delete_execute:{slug}")],
                [InlineKeyboardButton("❌ 취소", callback_data="btn_cancel_session")]
            ])
        )
        return

    if data.startswith("delete_execute:"):
        slug = data.split("delete_execute:", 1)[1]
        try:
            publisher = GitHubPublisher(config)
            deleted_title = publisher.delete_article(slug, human_approved=True)
            await query.edit_message_text(
                f"🗑️ <b>[게시글 삭제 완료]</b>\n━━━━━━━━━━━━━━━━━━━━\n"
                f"📌 <b>제목</b>: <b>{deleted_title}</b>\n"
                f"🔗 <b>슬러그</b>: <code>{slug}</code>\n\n"
                f"✅ <i>마크다운 파일, 썸네일, 본문 이미지가 삭제되고 Git에 커밋되었습니다.</i>",
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"글 삭제 실패: {e}")
            await query.edit_message_text(f"❌ 글 삭제 중 오류가 발생했습니다: {e}")
        return

    if data == "agent_list":
        mgr = AgentManager()
        text, reply_markup = format_agent_dashboard(mgr)
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=reply_markup)
        return

    if data.startswith("agent_view:"):
        key = data.split("agent_view:", 1)[1]
        mgr = AgentManager()
        text, reply_markup = format_agent_detail(mgr, key)
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=reply_markup)
        return

    if data.startswith("agent_start:"):
        key = data.split("agent_start:", 1)[1]
        mgr = AgentManager()
        ok, msg = mgr.start_agent(key)
        await query.answer(text="타이머 시작됨", show_alert=False)
        text, reply_markup = format_agent_detail(mgr, key)
        await query.edit_message_text(f"{msg}\n\n{text}", parse_mode="HTML", reply_markup=reply_markup)
        return

    if data.startswith("agent_stop:"):
        key = data.split("agent_stop:", 1)[1]
        mgr = AgentManager()
        ok, msg = mgr.stop_agent(key)
        await query.answer(text="타이머 일시중지됨", show_alert=False)
        text, reply_markup = format_agent_detail(mgr, key)
        await query.edit_message_text(f"{msg}\n\n{text}", parse_mode="HTML", reply_markup=reply_markup)
        return

    if data.startswith("agent_restart:"):
        key = data.split("agent_restart:", 1)[1]
        mgr = AgentManager()
        ok, msg = mgr.restart_agent(key)
        await query.answer(text="타이머 재시작됨", show_alert=False)
        text, reply_markup = format_agent_detail(mgr, key)
        await query.edit_message_text(f"{msg}\n\n{text}", parse_mode="HTML", reply_markup=reply_markup)
        return

    if data.startswith("agent_run:"):
        key = data.split("agent_run:", 1)[1]
        mgr = AgentManager()
        ok, msg = mgr.trigger_run_now(key)
        await query.answer(text="파이프라인 백그라운드 가동됨", show_alert=False)
        text, reply_markup = format_agent_detail(mgr, key)
        await query.edit_message_text(f"{msg}\n\n{text}", parse_mode="HTML", reply_markup=reply_markup)
        return

    if data == "btn_view_full_edit":
        session = sessions.get(chat_id)
        if session and session.get("data"):
            content = session["data"].get("markdown_content", "본문 없음")
            if len(content) > 3800:
                content = content[:3800] + "\n\n... (분량 초과로 일부 생략되었습니다) ..."
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"📖 [수정된 본문 전문 미리보기]\n\n{content}"
            )
        else:
            await context.bot.send_message(chat_id=chat_id, text="⚠️ 현재 확인 가능한 수정본이 없습니다.")
        return

async def post_init(application):
    commands = [
        BotCommand("agent", "에이전트 관리 (스케줄/시작/중지/실행)"),
        BotCommand("approve", "대기 초안 승인 및 배포"),
        BotCommand("cancel", "진행 중인 작업 취소 및 초기화"),
        BotCommand("delete", "발행된 글 삭제 (목록/슬러그)"),
        BotCommand("edit", "기존 글 내용 또는 URL 수정"),
        BotCommand("help", "사용 가이드 및 명령어 보기"),
        BotCommand("queue", "발행 대기 초안 목록 조회"),
        BotCommand("reject", "대기 초안 발행 보류"),
        BotCommand("review", "초안 AI 감수 보고서 조회"),
        BotCommand("status", "서버 상태, 스케줄 & 대기 큐 조회"),
        BotCommand("traffic", "실시간 클릭수 & 뷰 트래픽 보고서"),
        BotCommand("write", "새 블로그 글 작성 기획"),
    ]
    try:
        await application.bot.set_my_commands(commands)
        logger.info("✅ 텔레그램 봇 전체 명령어(set_my_commands) 알파벳순 등록 성공!")
    except Exception as e:
        logger.warning(f"set_my_commands 실패: {e}")

def main():
    if not BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN is not set.")
        return
        
    if configured_chat_id() is None:
        logger.error("TELEGRAM_CHAT_ID/configured chat_id is missing or invalid; bot is disabled.")
        return

    app = ApplicationBuilder().token(BOT_TOKEN).post_init(post_init).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", handle_help_command))
    app.add_handler(CommandHandler(["agent", "agents"], handle_agent_command))
    app.add_handler(CommandHandler("status", handle_status_command))
    app.add_handler(CommandHandler(["traffic", "views", "clicks", "report"], handle_traffic_command))
    app.add_handler(CommandHandler("cancel", handle_cancel))
    app.add_handler(CommandHandler("reset", handle_cancel))
    app.add_handler(CommandHandler("queue", handle_queue_command))
    app.add_handler(CommandHandler("approve", handle_approve_command))
    app.add_handler(CommandHandler("reject", handle_reject_command))
    app.add_handler(CommandHandler("review", handle_review_command))
    app.add_handler(CommandHandler("write", handle_write_command))
    app.add_handler(CommandHandler("edit", handle_edit_command))
    app.add_handler(CommandHandler("delete", handle_delete_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))
    app.add_handler(CallbackQueryHandler(button_callback))
    
    logger.info("🤖 텔레그램 인터랙티브 봇 데몬 시작...")
    app.run_polling()

if __name__ == '__main__':
    main()
