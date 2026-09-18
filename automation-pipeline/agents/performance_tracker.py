"""Site inventory and measured-only performance reporting.

Missing measurements are None. Legacy traffic_history.json contains estimates and
is deliberately neither read nor overwritten by this collector.
"""
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

import yaml

from integrations.google_adsense_api import GoogleAdSenseAPI


class PerformanceTracker:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.pipeline_dir = Path(__file__).resolve().parents[1]
        self.content_dir = str((self.pipeline_dir / config.get("github", {}).get(
            "blog_content_dir", "../blog-frontend/src/content/blog")).resolve())

    def _post_inventory(self) -> list:
        posts = []
        for path in Path(self.content_dir).glob("*.md"):
            try:
                content = path.read_text(encoding="utf-8")
                lines = content.splitlines()
                if not lines or lines[0] != "---":
                    continue
                end = lines.index("---", 1)
                meta = yaml.safe_load("\n".join(lines[1:end]))
                if not isinstance(meta, dict):
                    continue
                published = meta.get("pubDate") or meta.get("date")
                posts.append({
                    "slug": path.stem,
                    "title": str(meta.get("title") or path.stem),
                    "category": str(meta.get("category") or "일반"),
                    "date": str(published)[:10] if published else None,
                    "draft": meta.get("draft") is True or str(meta.get("draft", "")).lower() == "true",
                    "mtime": path.stat().st_mtime,
                })
            except (OSError, ValueError, yaml.YAMLError):
                continue
        return posts

    def count_posts(self) -> Dict[str, int]:
        inventory = self._post_inventory()
        public_posts = [p for p in inventory if not p["draft"]]
        today = datetime.now().date().isoformat()
        return {"total": len(public_posts),
                "today": sum(p["date"] == today for p in public_posts),
                "drafts": sum(p["draft"] for p in inventory)}

    def get_post_details(self) -> list:
        """Local public-post metadata; file mtime is never a publication date."""
        return sorted((p for p in self._post_inventory() if not p["draft"]),
                      key=lambda p: (p["date"] or "", p["slug"]), reverse=True)

    def get_site_statistics(self) -> Dict[str, Any]:
        counts = self.count_posts()
        return {"total_posts": counts["total"], "today_posts": counts["today"],
                "draft_posts": counts["drafts"], "post_count_source": "local_public_frontmatter",
                "pageviews": None, "est_pageviews": None, "indexed_pages": None,
                "traffic_status": "unavailable", "index_status": "unavailable",
                "uptime": "미확인", "deployment_status": "not_checked"}

    def get_click_view_statistics(self) -> Dict[str, Any]:
        """No blog analytics API exists in this legacy path; do not invent one.

        A measurement tag is configuration, not proof of successful collection.
        Repository views, article count and old estimates are never substitutes.
        """
        counts = self.count_posts()
        return {
            "date": datetime.now().date().isoformat(), "status": "unavailable",
            "reason": "blog_analytics_api_not_connected", "is_measured": False,
            "source": None, "today_views": None, "today_uv": None,
            "today_clicks": None, "ctr": None, "cumulative_views": None,
            "total_uniques_14d": None, "latest_active_date": None,
            "latest_active_views": None, "growth_vs_yesterday": None,
            "total_posts": counts["total"], "today_posts": counts["today"],
            "draft_posts": counts["drafts"], "category_views": {}, "top_posts": [],
            "sources": self.get_traffic_sources_status(),
        }

    def get_traffic_sources_status(self) -> Dict[str, Any]:
        analytics = self.config.get("analytics", {})
        seo = self.config.get("seo", {})
        goat_code = analytics.get("goatcounter_code") or seo.get("goatcounterCode") or os.getenv("PUBLIC_GOATCOUNTER_CODE")
        ga_id = analytics.get("ga_id") or seo.get("gaId") or os.getenv("PUBLIC_GA_ID")
        return {
            "github": {"name": "GitHub repository traffic", "status": "excluded",
                       "detail": "저장소 조회 통계는 블로그 방문 통계가 아니므로 제외"},
            "goatcounter": {"name": "GoatCounter", "status": "unavailable",
                            "detail": "태그 설정 있음 · API 수집 미연결" if goat_code else "설정 없음",
                            "dashboard": f"https://{goat_code}.goatcounter.com" if goat_code else None},
            "ga4": {"name": "Google Analytics 4", "status": "unavailable", "ga_id": ga_id,
                    "detail": "측정 ID 설정 있음 · API 수집 미연결" if ga_id else "설정 없음"},
        }

    def get_adsense_statistics(self) -> Dict[str, Any]:
        return GoogleAdSenseAPI(self.config).fetch_live_statistics()

    def get_system_health(self) -> Dict[str, Any]:
        cpu_temp = "미확인"
        disk_info = "미확인"
        try:
            raw = Path("/sys/class/thermal/thermal_zone0/temp").read_text().strip()
            cpu_temp = f"{int(raw) / 1000.0:.1f}°C"
        except (OSError, ValueError):
            pass
        try:
            st = os.statvfs("/")
            disk_info = f"{st.f_bavail * st.f_frsize / (1024 ** 3):.1f}GB 가용"
        except OSError:
            pass
        return {"cpu_temp": cpu_temp, "disk_free": disk_info,
                "git_status": "미확인", "timer_status": "미확인", "error_details": ""}
