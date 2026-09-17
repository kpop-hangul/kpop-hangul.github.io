import os
import json
import re
import random
from typing import List, Dict, Any
from templates.prompt_templates import KEYWORD_HARVESTER_SYSTEM_PROMPT
from integrations.antigravity_runner import AntigravityRunner

class KeywordHarvester:
    """
    GPT / Codex CLI 또는 RSS 트렌드를 분석하여
    수익화 및 SEO에 최적화된 블로그 포스팅 주제를 발굴하는 에이전트
    """

    def __init__(self, config: Dict[str, Any], api_key: str = None):
        self.config = config
        self.categories = config.get("content", {}).get("categories", [])
        self.api_key = None  # Retained constructor compatibility; Codex login supplies authentication.
        self.antigravity_runner = AntigravityRunner(config)
        self.rss_sources = [
            "https://feeds.feedburner.com/TechCrunch/",
            "https://news.ycombinator.com/rss",
            "https://www.theverge.com/rss/index.xml",
        ]

    def fetch_trending_keywords(self) -> List[str]:
        collected_titles = []
        try:
            import feedparser
            for url in self.rss_sources[:2]:
                try:
                    feed = feedparser.parse(url)
                    for entry in feed.entries[:5]:
                        collected_titles.append(entry.title)
                except Exception:
                    pass
        except ImportError:
            pass

        return collected_titles

    def harvest_from_csv_queue(self, target_category: str = None) -> Dict[str, Any]:
        """고단가 롱테일 키워드 큐(keywords.csv)에서 ready 상태의 키워드 1건을 선출"""
        csv_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "keywords.csv"))
        if not os.path.exists(csv_path):
            return None
        import csv
        category_names = {c.get("slug"): c.get("name") for c in self.categories}
        requested_name = category_names.get(target_category, target_category)
        try:
            with open(csv_path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for r in reader:
                    if r.get("status") == "ready":
                        if requested_name and requested_name != r.get("category", ""):
                            continue
                        keyword = r.get("keyword", "").strip()
                        if not keyword:
                            continue
                        category = r.get("category", "스마트 부업 & 재테크")
                        cpc = r.get("estimated_cpc", "2.5")
                        words = keyword.split()
                        target_kw = keyword
                        return {
                            "title": keyword,
                            "category": category,
                            "target_keyword": target_kw,
                            "tags": [category.split("&")[0].strip(), words[0]],
                            "search_intent": f"{keyword}에 관한 구체적인 질문에 답하기",
                            "key_points": [],  # Writer selects a structure for this topic, not CPC.
                            "_csv_keyword": keyword,
                            "_estimated_cpc": cpc
                        }
        except Exception as e:
            print(f"⚠️ keywords.csv 읽기 실패: {e}")
        return None

    def mark_csv_keyword_published(self, keyword: str, slug: str):
        """발행 완료된 키워드의 상태를 published로 갱신"""
        csv_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "keywords.csv"))
        if not os.path.exists(csv_path):
            return
        import csv
        from datetime import datetime
        rows = []
        try:
            with open(csv_path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                fieldnames = reader.fieldnames
                for r in reader:
                    if r.get("keyword") == keyword:
                        r["status"] = "published"
                        r["published_date"] = datetime.now().strftime("%Y-%m-%d")
                        r["post_slug"] = slug
                    rows.append(r)
            with open(csv_path, "w", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)
            print(f"✅ keywords.csv 상태 업데이트 완료: '{keyword}' ➔ published")
        except Exception as e:
            print(f"⚠️ keywords.csv 업데이트 실패: {e}")

    def harvest_ideas(self, target_category: str = None) -> List[Dict[str, Any]]:
        # 1. 고단가 롱테일 키워드 큐(keywords.csv) 우선 확인
        csv_topic = self.harvest_from_csv_queue(target_category)
        if csv_topic:
            print(f"🎯 [keywords.csv] 고단가 큐에서 우선 선출된 키워드: '{csv_topic['title']}' (예상 CPC: ${csv_topic.get('_estimated_cpc', '2.5')})")
            return [csv_topic]

        selected_cat = None
        if target_category:
            for cat in self.categories:
                if cat["slug"] == target_category or cat["name"] == target_category:
                    selected_cat = cat
                    break
        if not selected_cat and self.categories:
            selected_cat = random.choice(self.categories)

        category_name = selected_cat["name"] if selected_cat else "AI & 생산성"
        seed_keywords = selected_cat.get("keywords", []) if selected_cat else ["AI 자동화", "부업 블로그"]

        user_prompt = f"""
카테고리: {category_name}
시드 키워드 풀: {', '.join(seed_keywords)}
최근 트렌드 참고: {', '.join(self.fetch_trending_keywords()[:3])}

위 카테고리에서 독자가 해결하려는 구체적인 질문 3개를 기획하세요. 조사하지 않은 검색량, 광고 단가, 효능, 수익이나 소요시간은 단정하지 마세요. JSON 리스트로 반환하세요.
"""

        # 1. GPT / Codex CLI 우선 실행
        raw_output = self.antigravity_runner.generate_text(
            system_prompt=KEYWORD_HARVESTER_SYSTEM_PROMPT,
            user_prompt=user_prompt
        )

        if raw_output:
            try:
                clean_json = re.sub(r"^```json\s*", "", raw_output.strip())
                clean_json = re.sub(r"\s*```$", "", clean_json)
                ideas = json.loads(clean_json)
                if isinstance(ideas, list) and len(ideas) > 0:
                    return ideas
            except Exception:
                pass

        # 2. Gemini API 호출 시도

        # 3. Fallback 아이디어
        return self._generate_fallback_ideas(category_name, seed_keywords)

    def _generate_fallback_ideas(self, category, keywords):
        # No fabricated trends, numeric benefit claims, or unrelated default topics.
        return []
