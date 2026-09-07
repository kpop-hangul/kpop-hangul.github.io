import requests
from typing import Dict, Any

class GoogleIndexing:
    """
    새 글 배포 후 구글 서치콘솔에 사이트맵 핑을 전송하여
    구글봇의 신속한 크롤링과 색인을 요청하는 모듈
    """

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.site_url = config.get("site", {}).get("url", "https://yourusername.github.io").rstrip("/")

    def ping_sitemap(self) -> bool:
        """구글 및 빙에 사이트맵 업데이트 핑 전송"""
        sitemap_url = f"{self.site_url}/sitemap.xml"
        google_ping = f"https://www.google.com/ping?sitemap={sitemap_url}"
        bing_ping = f"https://www.bing.com/ping?sitemap={sitemap_url}"

        success = True
        try:
            r1 = requests.get(google_ping, timeout=5)
            print(f"📡 Google Sitemap Ping: {r1.status_code}")
        except Exception as e:
            print(f"Google Ping 알림: {e}")
            success = False

        try:
            r2 = requests.get(bing_ping, timeout=5)
            print(f"📡 Bing Sitemap Ping: {r2.status_code}")
        except Exception:
            pass

        return success
