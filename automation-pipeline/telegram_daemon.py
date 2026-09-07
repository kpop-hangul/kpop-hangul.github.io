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
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

from integrations.telegram_bot import _load_env_file, TelegramNotifier
from integrations.antigravity_runner import AntigravityRunner
from agents.performance_tracker import PerformanceTracker
from main_pipeline import load_config, KeywordHarvester, ContentWriter, PolicyInspector, GitHubPublisher, GoogleIndexing
import asyncio

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

config = load_config()
_load_env_file()
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# Chat session storage: { chat_id: { "state": ..., "topic": ..., "draft": ..., "slug": ..., "feedbacks": [...], "busy": ..., "action": ... } }
sessions = {}

raw_content_dir = config.get("github", {}).get("blog_content_dir", "../blog-frontend/src/content/blog")
CONTENT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), raw_content_dir))

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

async def handle_help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = """📚 <b>[앱시안 블로그 에이전트 명령어 & 사용 가이드]</b>
━━━━━━━━━━━━━━━━━━━━
🤖 <b>기본 명령어 목록:</b>

• <code>/status</code> : 라즈베리파이 상태, 타이머 스케줄, 발행 현황 및 대화 세션 조회
• <code>/write [주제/자료]</code> : 새로운 블로그 포스팅 기획 및 작성 시작
• <code>/edit [URL] [요청사항]</code> : 기존 블로그 포스팅 내용 또는 URL(슬러그) 수정
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
   • <code>https://absianp.github.io/blog/...</code> 링크와 함께 수정할 내용을 입력"""

    await update.message.reply_text(msg, parse_mode="HTML")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 <b>앱시안 인터랙티브 블로그 AI 에이전트에 오신 것을 환영합니다!</b>\n\n"
        "자유롭게 작성하고 싶은 <b>주제</b>나 <b>참고 링크/자료</b>를 채팅창에 보내주시면 글 작성이 시작됩니다.\n\n"
        "전체 명령어 및 사용 방법이 궁금하시면 언제든 <code>/help</code> 를 입력해 주세요! 🚀",
        parse_mode="HTML"
    )

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
            site_url = config.get("site", {}).get("url", "https://absianp.github.io")
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
            if "auto-blog.timer" in line:
                timer_details.append("  • 🤖 <b>일일 자동 포스팅</b>: 매일 <code>07:00 KST</code>")
            elif "auto-blog-geeknews.timer" in line:
                timer_details.append("  • 📰 <b>GeekNews 주간 브리핑</b>: 매주 금요일 <code>08:00 KST</code>")
            elif "auto-blog-dryrun.timer" in line:
                timer_details.append("  • 🩺 <b>이상 탐지 (Dryrun)</b>: <code>4시간 간격 (00, 04, 08, 12, 16, 20시)</code>")
            elif "auto-blog-morning.timer" in line:
                timer_details.append("  • 🌅 <b>아침 현황 브리핑</b>: 매일 <code>08:00 KST</code>")
            elif "auto-blog-evening.timer" in line:
                timer_details.append("  • 🌆 <b>저녁 수익 리포트</b>: 매일 <code>19:00 KST</code>")
    except Exception:
        pass
    
    if not timer_details:
        timer_details = [
            "  • 🤖 일일 자동 포스팅: 매일 07:00 KST",
            "  • 📰 GeekNews 주간 브리핑: 매주 금요일 08:00 KST",
            "  • 🩺 4시간 Dryrun 모의점검 활성",
            "  • 🌅 아침 08:00 / 저녁 19:00 브리핑"
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

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    msg = f"""📊 <b>[앱시안 블로그 에이전트 시스템 현황]</b> ({now_str})
━━━━━━━━━━━━━━━━━━━━
🍓 <b>라즈베리파이 5 서버 상태</b>
  • 🌡️ CPU 온도: <b>{cpu_temp}</b>
  • 💾 저장 공간: <b>{disk_free}</b>
  • ⚡ AI 엔진: {engine_status}
  • 🤖 텔레그램 데몬: <b>🟢 24/7 실시간 가동 중</b>

⏰ <b>자동화 에이전트 스케줄</b>
{timers_text}

📚 <b>블로그 콘텐츠 & 키워드 큐</b>
  • 총 포스트 수: <b>{total_posts}개</b> (+{today_posts}건 오늘 발행)
  • 📋 고단가 롱테일 큐: {queue_summary}
  • 최근 발행 글: {latest_post_info}

💬 <b>내 대화 세션 상태</b>
  • {session_text}"""

    keyboard = []
    if latest_post_url:
        keyboard.append([InlineKeyboardButton("🌐 최근 발행 글 보기", url=latest_post_url)])
    keyboard.append([InlineKeyboardButton("🏠 블로그 메인 홈", url=config.get("site", {}).get("url", "https://absianp.github.io"))])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(msg, parse_mode="HTML", reply_markup=reply_markup, disable_web_page_preview=True)

async def handle_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id in sessions:
        del sessions[chat_id]
        await update.message.reply_text("🔄 현재 작업 세션이 취소 및 초기화되었습니다. 새로운 주제를 언제든 입력해주세요!")
    else:
        await update.message.reply_text("ℹ️ 현재 진행 중인 작업 세션이 없습니다.")

async def handle_write_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = " ".join(context.args) if context.args else ""
    if not user_text:
        await update.message.reply_text("⚠️ 작성할 주제나 자료를 입력해주세요.\n예: /write 최근 AI 트렌드")
        return
    # Reset existing session and start new planning
    chat_id = update.effective_chat.id
    sessions[chat_id] = {"state": "PLANNING", "feedbacks": [user_text]}
    await generate_or_update_topic_plan(update.message, chat_id, user_text, context, is_update=False)

async def handle_edit_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = " ".join(context.args) if context.args else ""
    if not user_text:
        await update.message.reply_text("⚠️ 수정할 블로그 글 URL과 수정 요청사항을 함께 입력해주세요.\n예: /edit https://absianp.github.io/blog/2026-08-31-llm-qwen-27b/ 제목 변경해줘")
        return
    await route_message(update.message, user_text, context)

async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    await route_message(update.message, user_text, context)

async def route_message(message, user_text, context):
    chat_id = message.chat_id
    session = sessions.get(chat_id)

    # 1. Existing Blog Edit Request
    blog_url_match = re.search(r"absianp\.github\.io/blog/([^/\s?#]+)", user_text)
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
        system_prompt = "당신은 수익화 및 SEO 전문 블로그 기획 에이전트입니다. 오직 유효한 JSON 형식으로만 응답해야 합니다."

        # URL 링크가 포함된 경우 웹페이지 본문 및 목차 자동 수집
        url_match = re.search(r"https?://[^\s]+", user_input)
        url_context = ""
        if url_match:
            raw_url = url_match.group(0).rstrip(".,)")
            if not "github.com" in raw_url and not "absianp.github.io" in raw_url:
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
       "title": "클릭률과 검색 유입을 극대화하는 매력적인 제목 1",
       "category": "AI & 생산성",
       "target_keyword": "핵심 키워드",
       "tags": ["태그1", "태그2", "태그3"],
       "key_points": ["다룰 핵심 내용1", "핵심 내용2", "핵심 내용3"]
     }},
     {{
       "title": "매력적인 제목 2",
       "category": "개발 & 테크",
       "target_keyword": "핵심 키워드",
       "tags": ["태그1", "태그2"],
       "key_points": ["다룰 핵심 내용1", "핵심 내용2"]
     }}
   ]

2. 단일 글 작성 요청인 경우:
   단일 JSON 객체 형식으로 응답하세요:
   {{
     "title": "클릭률과 검색 유입을 극대화하는 매력적인 제목",
     "category": "AI & 생산성",
     "target_keyword": "핵심 롱테일 키워드",
     "tags": ["태그1", "태그2", "태그3", "태그4"],
     "key_points": ["핵심 포인트1", "포인트2", "포인트3"]
   }}

반드시 마크다운 코드블록(```json) 없이 순수한 JSON으로만 응답하세요.
"""
        raw_output = runner.generate_text(system_prompt=system_prompt, user_prompt=user_prompt)
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
                InlineKeyboardButton("🚀 즉시 발행 & 배포", callback_data="btn_quick_publish")
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

    topic_data = session["topic"]
    feedbacks = session.get("feedbacks", [])

    status_msg = await context.bot.send_message(
        chat_id=chat_id,
        text="✍️ <b>Antigravity 에이전트가 1,500자 이상 심층 아티클 초안을 작성 중입니다... (약 1~2분 소요)</b>",
        parse_mode="HTML"
    )

    session["busy"] = True
    session["action"] = "본문 1,500자 이상 심층 초안 작성 (Antigravity CLI)"
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
            f"📊 <b>품질 점수</b>: <code>{score}/100점</code> | 📏 <b>분량</b>: <code>{char_count:,}자</code>\n"
            f"⏱️ <b>소요 시간</b>: {article.get('readingTime', '6 min read')} | ❓ <b>FAQ</b>: {faqs_count}개\n\n"
            f"📖 <b>서론 미리보기</b>:\n"
            f"<i>\"{content_preview}...\"</i>\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"💡 <b>수정/첨언 방법</b>:\n"
            f"• 본문에 추가하고 싶은 내용, 수정할 점, 변경할 제목 등을 <b>메시지로 편하게 보내주시면 초안에 즉시 반영</b>됩니다!\n"
            f"• 내용이 마음에 드시면 아래 <b>[🚀 최종 발행 및 배포]</b> 버튼을 눌러주세요."
        )

        keyboard = [
            [InlineKeyboardButton("🚀 최종 발행 및 배포", callback_data="btn_publish_draft")],
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

    processing_msg = await message.reply_text("🔄 보내주신 피드백/자료를 반영하여 본문 초안을 수정 및 보강 중입니다...")

    current_draft = session["draft"]
    session["busy"] = True
    session["action"] = "본문 피드백/첨언 반영 및 수정 중 (Antigravity CLI)"
    session["started_at"] = time.time()
    sessions[chat_id] = session

    try:
        runner = AntigravityRunner(config)
        system_prompt = "당신은 전문 수석 테크 에디터입니다. 기존 초안에 사용자의 수정 요청 및 추가 자료를 완벽히 반영하여 업그레이드하고, 반드시 유효한 JSON 형식으로만 응답하세요."

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
        raw_output = runner.generate_text(system_prompt=system_prompt, user_prompt=user_prompt)
        if not raw_output:
            raise Exception("Antigravity 에디터로부터 응답을 받지 못했습니다.")

        updated_draft = extract_json(raw_output)
        session["draft"] = updated_draft
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
            [InlineKeyboardButton("🚀 최종 발행 및 배포", callback_data="btn_publish_draft")],
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
# STEP 3: PUBLISHING TO GITHUB PAGES
# -------------------------------------------------------------
async def execute_publish(chat_id, context, is_draft=True):
    session = sessions.get(chat_id)
    if not session:
        await context.bot.send_message(chat_id=chat_id, text="⚠️ 발행할 작업 세션을 찾을 수 없습니다.")
        return

    status_msg = await context.bot.send_message(
        chat_id=chat_id,
        text="🚀 <b>Astro 블로그 저장소에 마크다운을 커밋하고 GitHub Pages로 배포 중입니다...</b>",
        parse_mode="HTML"
    )

    try:
        writer = ContentWriter(config)
        publisher = GitHubPublisher(config)
        inspector = PolicyInspector(config)
        telegram = TelegramNotifier(config)
        indexer = GoogleIndexing(config)

        if is_draft and session.get("draft"):
            article = session["draft"]
        else:
            # Quick publish without draft review
            topic = session.get("topic")
            article = writer.write_article(topic)

        inspection = inspector.inspect_article(article)
        saved_path = publisher.publish_article(article)
        
        site_url = config.get("site", {}).get("url", "https://absianp.github.io")
        post_slug = os.path.splitext(os.path.basename(saved_path))[0]
        full_post_url = f"{site_url.rstrip('/')}/blog/{post_slug}/"

        indexer.ping_sitemap()
        telegram.send_article_published(article, inspection, full_post_url)

        # Clear session
        del sessions[chat_id]

        msg = f"""🎉 <b>[성공적으로 게시 및 배포 완료!]</b>
━━━━━━━━━━━━━━━━━━━━
📌 <b>제목</b>: <b>{article.get('title')}</b>
🏷️ <b>카테고리</b>: {article.get('category')}
📊 <b>품질 점수</b>: {inspection.get('score', 90)}점 ({inspection.get('char_count', 1500):,}자)

🔗 <b>글 바로가기</b>:
<a href="{full_post_url}">{full_post_url}</a>

✨ <i>GitHub Pages에 안전하게 배포되었으며 구글 검색엔진에 색인 요청되었습니다.</i>"""

        reply_markup = {
            "inline_keyboard": [
                [{"text": "🌐 게시글 확인하기", "url": full_post_url}]
            ]
        }
        await status_msg.edit_text(msg, parse_mode="HTML", reply_markup=reply_markup, disable_web_page_preview=False)

    except Exception as e:
        logger.error(f"Error in execute_publish: {e}")
        await status_msg.edit_text(f"❌ 배포 중 오류가 발생했습니다: {e}")

async def execute_batch_publish(chat_id, context):
    session = sessions.get(chat_id)
    if not session or not session.get("topics"):
        await context.bot.send_message(chat_id=chat_id, text="⚠️ 발행할 다중 포스팅 작업 세션을 찾을 수 없습니다.")
        return

    topics = session["topics"]
    total = len(topics)

    status_msg = await context.bot.send_message(
        chat_id=chat_id,
        text=f"🚀 <b>[다중 글 일괄 발행 시작 (총 {total}편)]</b>\n"
             f"Antigravity 에이전트가 각 챕터별 심층 글을 순차적으로 작성 및 배포합니다...",
        parse_mode="HTML"
    )

    session["busy"] = True
    session["action"] = f"다중 글({total}편) 순차 생성 및 배포"
    session["started_at"] = time.time()
    sessions[chat_id] = session

    try:
        writer = ContentWriter(config)
        publisher = GitHubPublisher(config)
        inspector = PolicyInspector(config)
        telegram = TelegramNotifier(config)
        indexer = GoogleIndexing(config)
        site_url = config.get("site", {}).get("url", "https://absianp.github.io")

        published_results = []

        for idx, topic in enumerate(topics):
            current_num = idx + 1
            await status_msg.edit_text(
                f"✍️ <b>[{current_num}/{total}편 심층 본문 작성 중...]</b>\n"
                f"📌 <b>{topic.get('title')}</b>\n"
                f"⏳ 약 1~2분 소요됩니다... (진행률: {int((idx/total)*100)}%)",
                parse_mode="HTML"
            )

            # Write article
            article = writer.write_article(topic)
            inspection = inspector.inspect_article(article)
            saved_path = publisher.publish_article(article)

            post_slug = os.path.splitext(os.path.basename(saved_path))[0]
            full_post_url = f"{site_url.rstrip('/')}/blog/{post_slug}/"
            published_results.append({
                "title": article.get("title"),
                "url": full_post_url,
                "score": inspection.get("score", 90),
                "char_count": inspection.get("char_count", 1500)
            })

            # Send Telegram alert for each article
            telegram.send_article_published(article, inspection, full_post_url)

        # Ping search console sitemap
        indexer.ping_sitemap()

        # Clear session
        if chat_id in sessions:
            del sessions[chat_id]

        summary_lines = "\n".join([
            f"{i+1}. <a href='{r['url']}'>{r['title']}</a> ({r['char_count']:,}자)"
            for i, r in enumerate(published_results)
        ])

        final_msg = f"""🎉 <b>[총 {total}편 일괄 포스팅 & 배포 완료!]</b>
━━━━━━━━━━━━━━━━━━━━
요청하신 모든 챕터별 아티클이 고품질로 성공적으로 작성되어 GitHub Pages에 배포되었습니다.

📚 <b>발행된 포스팅 목록:</b>
{summary_lines}

✨ 검색 엔진 색인 요청(핑)이 전송되었으며, 블로그 메인 화면 및 갤러리에서 즉시 확인하실 수 있습니다."""

        await status_msg.edit_text(final_msg, parse_mode="HTML", disable_web_page_preview=True)

    except Exception as e:
        logger.error(f"Error in execute_batch_publish: {e}")
        await status_msg.edit_text(f"❌ 다중 포스팅 처리 중 오류가 발생했습니다: {e}")
    finally:
        if chat_id in sessions:
            sessions[chat_id]["busy"] = False

# -------------------------------------------------------------
# STEP 4: EXISTING BLOG POST EDITING
# -------------------------------------------------------------
async def process_edit_input(message, user_text, blog_url_match, context, is_update=False):
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
        raw_output = runner.generate_text(system_prompt=system_prompt, user_prompt=user_prompt)
        if not raw_output:
            raise Exception("Antigravity 에디터로부터 응답을 받지 못했습니다.")

        modified_data = extract_json(raw_output)
        session["slug"] = slug
        session["data"] = modified_data
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
            [InlineKeyboardButton("🚀 최종 수정 및 재배포", callback_data="btn_apply_edit")],
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

async def execute_edit_publish(chat_id, context):
    session = sessions.get(chat_id)
    if not session or not session.get("data"):
        await context.bot.send_message(chat_id=chat_id, text="⚠️ 수정할 작업 세션이 없습니다.")
        return

    status_msg = await context.bot.send_message(
        chat_id=chat_id,
        text="✍️ <b>수정된 내용을 저장하고 GitHub Pages에 재배포 중입니다...</b>",
        parse_mode="HTML"
    )

    try:
        slug = session["slug"]
        article_data = session["data"]
        new_slug = article_data.get("new_slug")
        publisher = GitHubPublisher(config)
        indexer = GoogleIndexing(config)
        
        saved_path, final_slug = publisher.update_existing_article(slug, article_data, new_slug=new_slug)
        site_url = config.get("site", {}).get("url", "https://absianp.github.io")
        full_post_url = f"{site_url.rstrip('/')}/blog/{final_slug}/"
        
        indexer.ping_sitemap()
        
        del sessions[chat_id]

        slug_changed_note = f"\n🔗 <b>새 URL</b>: <a href=\"{full_post_url}\">{full_post_url}</a>\n" if final_slug != slug else ""

        msg = f"""🎉 <b>[포스팅 수정 및 재배포 완료]</b>
━━━━━━━━━━━━━━━━━━━━
📌 <b>제목</b>: <b>{article_data.get('title')}</b>
💡 <b>수정 사항</b>: {article_data.get('change_summary', '수정 완료')}{slug_changed_note}
🔗 <b>글 바로가기</b>:
<a href="{full_post_url}">{full_post_url}</a>

✨ <i>GitHub Pages에 성공적으로 반영 및 재배포되었습니다!</i>"""

        reply_markup = {
            "inline_keyboard": [
                [{"text": "🌐 수정된 글 확인하기", "url": full_post_url}]
            ]
        }
        await status_msg.edit_text(msg, parse_mode="HTML", reply_markup=reply_markup, disable_web_page_preview=False)

    except Exception as e:
        logger.error(f"Error in execute_edit_publish: {e}")
        await status_msg.edit_text(f"❌ 수정 배포 중 오류가 발생했습니다: {e}")

# -------------------------------------------------------------
# BUTTON CALLBACK HANDLER
# -------------------------------------------------------------
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    chat_id = query.message.chat_id

    if data == "btn_cancel_session":
        if chat_id in sessions:
            del sessions[chat_id]
        await query.edit_message_text("❌ 작업 세션이 취소되었습니다.")
        return

    if data == "btn_create_draft":
        await query.edit_message_text("✍️ 초안 작성을 시작합니다...")
        asyncio.create_task(create_article_draft(chat_id, query.message.message_id, context))
        return

    if data == "btn_quick_publish":
        await query.edit_message_text("🚀 즉시 작성 및 배포를 시작합니다...")
        asyncio.create_task(execute_publish(chat_id, context, is_draft=False))
        return

    if data == "btn_batch_publish":
        await query.edit_message_text("🚀 다중 포스팅 일괄 생성 및 순차 배포를 시작합니다...")
        asyncio.create_task(execute_batch_publish(chat_id, context))
        return

    if data == "btn_publish_draft":
        await query.edit_message_text("🚀 초안을 최종 승인하여 GitHub에 배포합니다...")
        asyncio.create_task(execute_publish(chat_id, context, is_draft=True))
        return

    if data == "btn_apply_edit":
        await query.edit_message_text("✍️ 수정 사항을 적용하여 재배포합니다...")
        asyncio.create_task(execute_edit_publish(chat_id, context))
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

def main():
    if not BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN is not set.")
        return
        
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", handle_help_command))
    app.add_handler(CommandHandler("status", handle_status_command))
    app.add_handler(CommandHandler("cancel", handle_cancel))
    app.add_handler(CommandHandler("reset", handle_cancel))
    app.add_handler(CommandHandler("write", handle_write_command))
    app.add_handler(CommandHandler("edit", handle_edit_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))
    app.add_handler(CallbackQueryHandler(button_callback))
    
    logger.info("🤖 텔레그램 인터랙티브 봇 데몬 시작...")
    app.run_polling()

if __name__ == '__main__':
    main()
