import feedparser
import requests
from bs4 import BeautifulSoup
from datetime import datetime
import urllib.parse
import ssl

if hasattr(ssl, '_create_unverified_context'):
    ssl._create_default_https_context = ssl._create_unverified_context

class GoogleNewsCrawler:
    def __init__(self):
        self.base_url = "https://news.google.com/rss/search"

    def fetch_top_news(self, keyword, num_articles=5):
        """
        주어진 키워드로 구글 뉴스 RSS를 검색하고 상위 N개의 기사를 반환합니다.
        """
        encoded_keyword = urllib.parse.quote(keyword)
        # 한국 뉴스 검색 URL
        url = f"{self.base_url}?q={encoded_keyword}&hl=ko&gl=KR&ceid=KR:ko"
        
        feed = feedparser.parse(url)
        articles = []
        
        for entry in feed.entries[:num_articles]:
            title = entry.title
            link = entry.link
            pub_date = entry.published
            
            # description(Snippet)에서 HTML 태그 제거
            raw_summary = entry.description if 'description' in entry else ""
            soup = BeautifulSoup(raw_summary, "html.parser")
            summary = soup.get_text(separator=" ").strip()
            
            articles.append({
                "title": title,
                "link": link,
                "pub_date": pub_date,
                "summary": summary
            })
            
        return articles

if __name__ == "__main__":
    crawler = GoogleNewsCrawler()
    news = crawler.fetch_top_news("인공지능", 3)
    for n in news:
        print(f"[제목] {n['title']}")
        print(f"[요약] {n['summary']}")
        print('---')
