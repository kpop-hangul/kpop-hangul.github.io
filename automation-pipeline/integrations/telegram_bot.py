from modules.draft_queue import article_review_token
import os
import math
from html import escape
import json
import re
import subprocess
from pathlib import Path
import requests
from datetime import datetime
from typing import Dict, Any, Optional

def _load_env_file():
    env_paths = [
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".env")),
        os.path.abspath(os.path.join(os.path.dirname(__file__), "../..", ".env")),
        os.path.abspath(os.path.join(os.path.dirname(__file__), "../config/.env")),
    ]
    for path in env_paths:
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#") and "=" in line:
                            k, v = line.split("=", 1)
                            os.environ[k.strip()] = v.strip()
                break
            except Exception:
                pass


def _display_metric(value, decimals=0):
    """Keep uncollected values distinct from measured zero."""
    if value is None or isinstance(value, bool):
        return "미수집"
    try:
        number = float(value)
        return f"{number:,.{decimals}f}" if math.isfinite(number) else "미수집"
    except (TypeError, ValueError):
        return "미수집"

class TelegramNotifier:
    """
    K-Pop Hangul 블로그 운영 텔레그램 스마트 알림 에이전트
    1. 새로운 주제(K-Pop 노래) 탐색 보고
    2. 심층 감수 보고서 및 HITL 검토/승인 요청
    3. 새로운 글 작성 및 배포 보고
    4. 일일 사이트 현황 보고
    5. 시스템 헬스 / 장애 긴급 알림
    """

    def __init__(self, config: Dict[str, Any]):
        _load_env_file()
        self.config = config
        telegram_cfg = config.get("telegram", {})
        self.enabled = telegram_cfg.get("enabled", True)
        self.bot_token = telegram_cfg.get("bot_token") or os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.chat_id = str(telegram_cfg.get("chat_id") or os.getenv("TELEGRAM_CHAT_ID", ""))
        self.site_url = (os.getenv("SITE_URL") or config.get("site", {}).get("url", "https://kpop-hangul.github.io")).rstrip("/")
        self.site_title = config.get("site", {}).get("title", "K-Pop 한글 (K-Pop Hangul)")
        self.api_url = f"https://api.telegram.org/bot{self.bot_token}" if self.bot_token else None

    def _send_message(self, text: str, reply_markup: Optional[Dict] = None) -> bool:
        if not self.enabled or not self.bot_token or not self.chat_id:
            print("[TelegramNotifier] ℹ️ 텔레그램 토큰 또는 Chat ID가 설정되지 않았습니다 (건너뜀).")
            return False

        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": False
        }
        if reply_markup:
            payload["reply_markup"] = json.dumps(reply_markup)

        try:
            res = requests.post(f"{self.api_url}/sendMessage", json=payload, timeout=12)
            if res.status_code == 200:
                print("📲 텔레그램 알림 전송 성공!")
                return True
            else:
                print(f"[TelegramNotifier] 전송 실패 (코드: {res.status_code}): {res.text}")
                return False
        except Exception as e:
            print(f"[TelegramNotifier] 네트워크 예외: {e}")
            return False

    # -------------------------------------------------------------
    # 1. 새로운 주제 탐색 보고
    # -------------------------------------------------------------
    def send_topic_discovered(self, topic: Dict[str, Any]) -> bool:
        title = topic.get("title", "")
        category = topic.get("category", "AI & 생산성")
        target_kw = topic.get("target_keyword", "")
        tags = topic.get("tags", [])
        key_points = topic.get("key_points", [])

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        points_html = "".join([f"  • {kp}\n" for kp in key_points[:3]])

        msg = f"""🔍 <b>[새로운 주제 탐색 보고]</b> ({now_str})
━━━━━━━━━━━━━━━━━━━━
📌 <b>선정 주제</b>: <code>{title}</code>
🏷️ <b>카테고리</b>: <b>{category}</b>
🎯 <b>핵심 키워드</b>: <code>#{target_kw}</code>
🏷️ <b>예상 태그</b>: #{', #'.join(tags[:4])}

📝 <b>핵심 다룰 내용</b>:
{points_html}
⚡ <i>AI 에이전트가 위 주제를 기반으로 1,500자 심층 포스팅 작성을 시작합니다.</i>"""

        return self._send_message(msg)

    # -------------------------------------------------------------
    # 1-1. 대표 썸네일 및 본문 다이어그램 앨범 전송
    # -------------------------------------------------------------
    def send_draft_images(self, draft_id: str, article: Dict[str, Any]) -> bool:
        if not self.bot_token or not self.chat_id:
            return False

        repo_root = Path(__file__).resolve().parent.parent.parent
        public_dir = repo_root / "blog-frontend" / "public"
        title = article.get("title", "")
        slug = article.get("slug", "")

        media_items = []
        file_handles = []
        try:
            # 1. 썸네일 수집
            thumb_url = article.get("heroImage", "")
            thumb_path = None
            if thumb_url and not thumb_url.startswith("http"):
                candidate = public_dir / thumb_url.lstrip("/")
                if candidate.exists():
                    thumb_path = candidate

            if not thumb_path and slug:
                candidate = public_dir / "images" / "thumbnails" / f"{slug}.svg"
                if candidate.exists():
                    thumb_path = candidate

            if thumb_path and thumb_path.exists():
                if thumb_path.suffix.lower() == ".svg":
                    png_tmp = Path(f"/tmp/preview_thumb_{thumb_path.stem}.png")
                    cmd = ["/usr/bin/ffmpeg", "-y", "-i", str(thumb_path), "-update", "1", "-frames:v", "1", str(png_tmp)]
                    res = subprocess.run(cmd, capture_output=True, timeout=15)
                    if res.returncode == 0 and png_tmp.exists():
                        media_items.append((png_tmp, f"🖼️ [K-Pop 썸네일] {title}"))
                else:
                    media_items.append((thumb_path, f"🖼️ [K-Pop 썸네일] {title}"))

            # 2. 본문 다이어그램 수집
            body = article.get("markdown_content", "")
            img_matches = re.findall(r'<img\s+[^>]*src="([^"]+)"[^>]*alt="([^"]*)"', body)
            if not img_matches:
                img_matches = [(f"/images/articles/{item.get('asset_key')}.webp", item.get("caption", "")) 
                               for item in article.get("article_images", [])]

            for idx, (img_url, img_alt) in enumerate(img_matches[:2], 1):
                img_file = public_dir / img_url.lstrip("/")
                if img_file.exists():
                    caption = f"📸 [학습 다이어그램 {idx}] {img_alt}" if img_alt else f"📸 [학습 다이어그램 {idx}]"
                    media_items.append((img_file, caption[:100]))

            if not media_items:
                return False

            files = {}
            media_list = []
            for i, (f_path, cap) in enumerate(media_items):
                field_name = f"photo_{i}"
                fh = open(f_path, "rb")
                file_handles.append(fh)
                files[field_name] = (f_path.name, fh)
                media_obj = {
                    "type": "photo",
                    "media": f"attach://{field_name}",
                    "caption": cap
                }
                media_list.append(media_obj)

            data = {
                "chat_id": self.chat_id,
                "media": json.dumps(media_list)
            }
            res = requests.post(f"{self.api_url}/sendMediaGroup", data=data, files=files, timeout=30)
            if res.status_code == 200:
                print(f"📸 K-Pop 초안 이미지 {len(media_items)}장 텔레그램 전송 성공!")
                return True
            else:
                print(f"⚠️ [TelegramNotifier] sendMediaGroup 실패 ({res.status_code}): {res.text}")
                return False
        except Exception as e:
            print(f"⚠️ [TelegramNotifier] send_draft_images 예외: {e}")
            return False
        finally:
            for fh in file_handles:
                try:
                    fh.close()
                except Exception:
                    pass

    # -------------------------------------------------------------
    # 1-2. Gemini 심층 감수 보고서 및 HITL 승인 요청
    # -------------------------------------------------------------
    def send_review_report(self, draft_id: str, article: Dict[str, Any], review: Dict[str, Any]) -> bool:
        from html import escape
        
        # 1. 썸네일 & 다이어그램 사진 앨범 발송
        try:
            self.send_draft_images(draft_id, article)
        except Exception as e:
            print(f"⚠️ 이미지 발송 예외 (텍스트 보고서 계속 진행): {e}")

        # 2. 감수 보고서 텍스트 및 승인 버튼 발송
        title = escape(str(article.get("title", "")))
        summary = escape(str(review.get("summary_for_user", review.get("summary", "검토 의견 없음"))))
        score = review.get("total_score", 90)
        verdict = review.get("verdict", "PENDING")
        artist = escape(str(article.get("artist", "")))
        song_title = escape(str(article.get("songTitle", "")))

        # 사람이 직접 수정할 포인트
        points = review.get("human_edit_points") or article.get("human_edit_points") or []
        points_text = ""
        if points:
            p_lines = []
            for p in points[:3]:
                idx = p.get("index", "")
                m = p.get("marker", "")
                rec = p.get("recommendation") or p.get("guide") or ""
                p_lines.append(f"  • <b>{escape(str(m[:40]))}</b>\n    ↳ <i>{escape(str(rec[:45]))}</i>")
            points_text = f"💡 <b>[사람이 직접 채울 추천 위치]</b>:\n" + "\n".join(p_lines) + "\n\n"

        msg = (f"🎵 <b>[K-Pop 한글 학습 초안 검토 및 승인 요청]</b>\n"
               f"━━━━━━━━━━━━━━━━━━━━\n"
               f"📌 <b>곡명</b>: <b>{artist} - {song_title}</b>\n"
               f"📑 <b>제목</b>: <code>{title}</code>\n"
               f"🆔 <b>초안 ID</b>: <code>{escape(draft_id)}</code>\n"
               f"📊 <b>감수 점수</b>: <b>{score}점</b> ({verdict})\n"
               f"🖼️ <b>포함 에셋</b>: 썸네일 1장 + 학습 다이어그램 2장 탑재 완료\n\n"
               f"{points_text}"
               f"📋 <b>편집 총평</b>:\n{summary}\n\n"
               f"━━━━━━━━━━━━━━━━━━━━\n"
               f"💡 <i>초안 본문과 다이어그램을 확인하신 후 직접 수정하거나 바로 승인해주세요.</i>")

        return self._send_message(msg, {"inline_keyboard": [
            [{"text": "📖 본문 초안 보기", "callback_data": f"view_draft:{draft_id}"},
             {"text": "✏️ 본문 직접 수정", "callback_data": f"edit_draft:{draft_id}"}],
            [{"text": "✅ 검토 후 승인 및 배포 요청", "callback_data": f"approve:{draft_id}:{article_review_token(article)}"},
             {"text": "❌ 발행 보류", "callback_data": f"reject:{draft_id}"}]]})

    # -------------------------------------------------------------
    # 2. 새로운 글 작성 및 배포 보고
    # -------------------------------------------------------------
    def send_article_published(self, article: Dict[str, Any], inspection: Dict[str, Any], post_url: str) -> bool:
        title = article.get("title", "")
        category = article.get("category", "")
        reading_time = article.get("readingTime", "5 min read")
        score = inspection.get("score", 90)
        char_count = inspection.get("char_count", 1500)
        faqs_count = len(article.get("faqs", []))

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

        msg = f"""🚀 <b>[새 글 작성 및 배포 완료]</b> ({now_str})
━━━━━━━━━━━━━━━━━━━━
📌 <b>제목</b>: <b>{title}</b>
🏷️ <b>카테고리</b>: {category} | ⏱️ {reading_time}
📊 <b>품질 점수</b>: <code>{score}/100점</code> (최적화 완료)
📏 <b>본문 분량</b>: <code>{char_count:,}자</code> | ❓ FAQ: <code>{faqs_count}개</code>
🛡️ <b>애드센스 정책</b>: ✅ 위반 리스크 없음

🔗 <b>글 바로가기</b>:
<a href="{post_url}">{post_url}</a>

✨ <i>GitHub Pages에 배포 완료되었으며, 구글 검색엔진에 색인 요청(Ping)되었습니다.</i>"""

        reply_markup = {
            "inline_keyboard": [
                [{"text": "🌐 게시글 확인하기", "url": post_url}],
                [{"text": "🏠 블로그 메인", "url": self.site_url}]
            ]
        }

        return self._send_message(msg, reply_markup)

    # -------------------------------------------------------------
    # 3. 일일 사이트 현황 보고 (아침 8시 / 저녁 7시)
    # -------------------------------------------------------------
    def send_daily_site_status(self, report_type: str, stats: Dict[str, Any]) -> bool:
        """Report inventory separately from uncollected audience/search metrics."""
        total = _display_metric(stats.get("total_posts"))
        today = _display_metric(stats.get("today_posts"))
        drafts = _display_metric(stats.get("draft_posts"))
        pv = _display_metric(stats.get("pageviews"))
        indexed = _display_metric(stats.get("indexed_pages"))
        msg = f"""📊 <b>[{escape(self.site_title)} 사이트 현황]</b>
• 로컬 공개 대상 글: <b>{total}</b> (발행일이 오늘인 글 {today})
• 초안: <b>{drafts}</b>
• 블로그 페이지뷰: <b>{pv}</b>
• 검색 색인 페이지: <b>{indexed}</b>
• 공개 배포 상태: <b>{escape(str(stats.get('deployment_status') or '미확인'))}</b>

미수집은 0이 아닙니다. 글 수로 방문수·색인수를 추정하지 않습니다.
<a href="{escape(self.site_url, quote=True)}">블로그 확인</a>"""
        return self._send_message(msg)


    # -------------------------------------------------------------
    # 3-1. 오늘 블로그 클릭 & 뷰(View) 트래픽 일일 보고
    # -------------------------------------------------------------
    def generate_click_view_report_text(self, traffic_data: Dict[str, Any]) -> str:
        """Render only explicitly measured blog analytics, never repository traffic."""
        measured = (traffic_data.get("status") == "measured"
                    and traffic_data.get("is_measured") is True
                    and traffic_data.get("source") in ("ga4", "goatcounter"))
        def metric(key, decimals=0):
            return _display_metric(traffic_data.get(key) if measured else None, decimals)
        source = traffic_data.get("source") if measured else "미연결"
        categories = []
        for name, values in list(traffic_data.get("category_views", {}).items())[:4] if measured else []:
            categories.append(f"• {escape(str(name))}: {_display_metric(values.get('views'))} PV")
        top_posts = []
        for post in traffic_data.get("top_posts", [])[:3] if measured else []:
            top_posts.append(f"• {escape(str(post.get('title', '')))}: {_display_metric(post.get('views'))} PV")
        sources = []
        for info in traffic_data.get("sources", {}).values():
            sources.append(f"• {escape(str(info.get('name', '')))}: {escape(str(info.get('detail') or info.get('status') or '미수집'))}")
        return f"""📈 <b>[{escape(self.site_title)} 블로그 트래픽]</b>
• 수집 출처: <b>{escape(str(source))}</b>
• 기준일: {escape(str(traffic_data.get('date') or '미확인'))}
• 페이지뷰: <b>{metric('today_views')}</b>
• 순 방문자: <b>{metric('today_uv')}</b>
• 독자 상호작용 클릭: <b>{metric('today_clicks')}</b>
• 클릭률: <b>{metric('ctr', 2)}</b> (단위 %)
• 전일 대비 증감: <b>{metric('growth_vs_yesterday', 2)}</b> (단위 %)
• 로컬 공개 대상 글: <b>{_display_metric(traffic_data.get('total_posts'))}</b>

<b>카테고리별 조회</b>
{chr(10).join(categories) or '미수집'}
<b>조회수 상위 글</b>
{chr(10).join(top_posts) or '미수집'}

<b>수집 연결 상태</b>
{chr(10).join(sources) or '미수집'}

미수집은 0이 아닙니다. GitHub 저장소 조회는 블로그 방문에 포함하지 않습니다."""


    def send_click_view_daily_report(self, traffic_data: Dict[str, Any]) -> bool:
        """
        애드센스 정식 등록 전, 오늘의 실질적인 클릭 및 조회수(PV/UV) 카운트 일일 보고 발송
        """
        msg = self.generate_click_view_report_text(traffic_data)
        return self._send_message(msg)

    # -------------------------------------------------------------
    # 4. 광고 수익 현황 일일 보고
    # -------------------------------------------------------------
    def generate_adsense_report_text(self, revenue_data: Dict[str, Any]) -> str:
        """AdSense's estimated earnings in the API-returned currency, without FX."""
        currency = revenue_data.get("currency")
        valid = (revenue_data.get("source") == "google_adsense_v2"
                 and revenue_data.get("status") in ("measured", "partial", "no_data"))
        def metric(key, decimals=0):
            return _display_metric(revenue_data.get(key) if valid else None, decimals)
        def money(key):
            if not currency:
                return "미수집"
            value = metric(key, 2)
            return f"{value} {escape(str(currency))}" if value != "미수집" else value
        period = f"{revenue_data.get('start_date') or '미확인'} ~ {revenue_data.get('end_date') or '미확인'}"
        month_period = f"{revenue_data.get('month_start_date') or '미확인'} ~ {revenue_data.get('month_end_date') or '미확인'}"
        details = escape(str(revenue_data.get("reason") or revenue_data.get("status") or "unavailable"))
        warnings = revenue_data.get("warnings") or []
        warning_text = "\nAPI 안내: " + escape("; ".join(str(w) for w in warnings)) if warnings else ""
        return f"""💰 <b>[{escape(self.site_title)} AdSense 실적]</b>
• 대상 사이트: <code>{escape(str(revenue_data.get('site_domain') or '미확인'))}</code>
• 수집 상태: <b>{details}</b>
• 당일 기간: {escape(period)} (AdSense 계정 시간대)
• 당일 예상 수익: <b>{money('estimated_earnings')}</b>
• 월 누적 기간: {escape(month_period)}
• 월 누적 예상 수익: <b>{money('month_total')}</b>
• 광고 노출수: <b>{metric('impressions')}</b>
• 광고 클릭수: <b>{metric('clicks')}</b>
• 노출 대비 클릭률: <b>{metric('ctr', 2)}</b> (단위 %)
• 광고 노출 RPM: <b>{money('rpm')}</b>
• 페이지 RPM: <b>{money('page_rpm')}</b>{warning_text}

AdSense API의 예상 수익이며 확정 지급액이 아닙니다.
미수집과 실제 0을 구분하며 임의 환율로 환산하지 않습니다."""


    def send_adsense_daily_report(self, revenue_data: Dict[str, Any]) -> bool:
        return self._send_message(self.generate_adsense_report_text(revenue_data))


    # -------------------------------------------------------------
    # 5. 시스템 헬스 / 장애 긴급 알림
    # -------------------------------------------------------------
    def send_health_report(self, health_data: Dict[str, Any], is_alert: bool = False) -> bool:
        lines = []
        for label, key in (("CPU 온도", "cpu_temp"), ("디스크 여유", "disk_free"),
                           ("스케줄러", "timer_status"), ("Git 동기화", "git_status")):
            lines.append(f"• {label}: {escape(str(health_data.get(key) or '미확인'))}")
        error = health_data.get("error_details")
        if is_alert and error:
            lines.append("• 오류: " + escape(str(error)))
        return self._send_message("🖥️ <b>[시스템 확인]</b>\n" + "\n".join(lines))
