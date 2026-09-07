import subprocess
import xml.etree.ElementTree as ET
import json
import re
from datetime import datetime, timedelta
from integrations.antigravity_runner import AntigravityRunner

class GeekNewsHarvester:
    def __init__(self, config: dict):
        self.config = config
        self.runner = AntigravityRunner(config)

    def fetch_weekly_articles(self) -> list:
        """GeekNews RSS 및 최근 피드에서 지난 7일간의 테크/AI 기사를 수집"""
        feed_url = "https://news.hada.io/rss/news"
        articles = []
        try:
            cmd = ["curl", "-s", "-A", "Mozilla/5.0", feed_url]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            root = ET.fromstring(res.stdout)
            ns = {"atom": "http://www.w3.org/2005/Atom"}

            for entry in root.findall("atom:entry", ns):
                title = entry.find("atom:title", ns)
                link = entry.find("atom:link", ns)
                published = entry.find("atom:published", ns)
                content = entry.find("atom:content", ns)
                
                title_text = title.text.strip() if title is not None and title.text else ""
                link_href = link.attrib.get("href", "") if link is not None else ""
                pub_date = published.text.strip() if published is not None and published.text else ""
                content_text = content.text.strip() if content is not None and content.text else ""
                
                # HTML 태그 제거
                clean_content = re.sub(r"<[^>]+>", " ", content_text).strip()
                clean_content = re.sub(r"\s+", " ", clean_content)

                articles.append({
                    "title": title_text,
                    "link": link_href,
                    "published": pub_date,
                    "content": clean_content[:300]
                })
        except Exception as e:
            print(f"⚠️ GeekNews RSS 수집 중 오류: {e}")
        
        return articles

    def harvest_weekly_briefing_topic(self) -> dict:
        """수집된 기사들을 기반으로 Antigravity AI를 통해 주간 브리핑 기획안 생성"""
        articles = self.fetch_weekly_articles()
        
        if not articles:
            articles_summary = "최신 AI 모델 동향, 오픈소스 개발 도구, 소프트웨어 엔지니어링 아키텍처 및 생산성 도구 트렌드"
        else:
            articles_summary = "
".join([
                f"- [{a['published'][:10]}] {a['title']}: {a['content']}"
                for a in articles[:30]
            ])

        now = datetime.now()
        year = now.year
        month = now.month
        week_num = (now.day - 1) // 7 + 1
        date_str = now.strftime("%Y-%m-%d")

        system_prompt = """당신은 국내 최고 수준의 테크 전문 에디터이자 GeekNews(긱뉴스) 큐레이터입니다.
한 주간의 개발자 커뮤니티 핵심 뉴스와 AI/오픈소스 트렌드를 관통하는 심층 주간 테크 브리핑 기획안을 작성해야 합니다.
반드시 유효한 JSON 형식으로만 응답하세요."""

        user_prompt = f"""
[GeekNews 이번 주 수집 기사 목록]
{articles_summary}

현재 기준: {year}년 {month}월 {week_num}주차

위 수집된 기사들 중 개발자와 테크 종사자들에게 가장 임팩트 있고 실용적인 핵심 테마 3~5개를 선별하여,
독자들의 클릭을 유도하고 깊이 있는 인사이트를 전달할 주간 테크 브리핑 기획안을 JSON으로 작성해주세요.

출력 JSON 형식:
{{
  "title": "{year}년 {month}월 {week_num}주차 긱뉴스(GeekNews) 주간 테크 브리핑: [핵심 테마 요약]",
  "category": "개발 & 테크",
  "target_keyword": "긱뉴스 주간 브리핑 {year}년 {month}월",
  "tags": ["긱뉴스", "GeekNews", "주간테크", "AI트렌드", "오픈소스", "개발자생산성"],
  "slug": "{date_str}-geeknews-weekly-{year}-{month}w{week_num}",
  "key_points": [
    "이번 주 GeekNews를 달군 핵심 AI & 오픈소스 도구 분석",
    "실무 엔지니어링 및 개발 생산성 관점에서의 시사점",
    "새롭게 주목받은 라이브러리 및 인프라 기술 리뷰",
    "개발자를 위한 한 줄 요약 및 실무 적용 가이드"
  ]
}}
"""
        raw_output = self.runner.generate_text(system_prompt=system_prompt, user_prompt=user_prompt)
        
        try:
            json_match = re.search(r"\{[\s\S]*\}", raw_output)
            clean_json = json_match.group(0) if json_match else raw_output.strip()
            topic = json.loads(clean_json)
            if not topic.get("slug"):
                topic["slug"] = f"{date_str}-geeknews-weekly-{year}-{month}w{week_num}"
            return topic
        except Exception as e:
            print(f"⚠️ JSON 파싱 실패: {e}")
            return {
                "title": f"{year}년 {month}월 {week_num}주차 긱뉴스(GeekNews) 주간 테크 브리핑: 최신 AI & 오픈소스 트렌드",
                "category": "개발 & 테크",
                "target_keyword": f"긱뉴스 주간 브리핑 {year}년 {month}월",
                "tags": ["긱뉴스", "GeekNews", "주간테크", "AI트렌드", "오픈소스", "개발자생산성"],
                "slug": f"{date_str}-geeknews-weekly-{year}-{month}w{week_num}",
                "key_points": [
                    "이번 주 GeekNews를 달군 핵심 AI & 오픈소스 도구 분석",
                    "실무 엔지니어링 및 개발 생산성 관점에서의 시사점",
                    "새롭게 주목받은 라이브러리 및 인프라 기술 리뷰",
                    "개발자를 위한 한 줄 요약 및 실무 적용 가이드"
                ]
            }
