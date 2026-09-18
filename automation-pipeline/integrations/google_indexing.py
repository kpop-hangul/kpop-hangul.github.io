"""Check sitemap availability; this does not submit URLs or confirm indexing."""
import requests
from xml.etree import ElementTree


class GoogleIndexing:
    def __init__(self, config):
        self.site_url = config.get("site", {}).get("url", "").rstrip("/")

    def check_sitemap(self):
        for name in ("sitemap-index.xml", "sitemap.xml"):
            url = f"{self.site_url}/{name}"
            try:
                response = requests.get(url, timeout=5, allow_redirects=False)
                if response.status_code == 200 and ElementTree.fromstring(response.content).tag.split("}")[-1] in ("sitemapindex", "urlset"):
                    return {"available": True, "url": url, "indexing_status": "unknown",
                            "message": "사이트맵 응답 확인. 색인 여부는 Search Console에서 확인해야 합니다."}
            except (requests.RequestException, ElementTree.ParseError):
                continue
        return {"available": False, "indexing_status": "unknown", "message": "사이트맵 응답을 확인하지 못했습니다."}

    def ping_sitemap(self):
        """Compatibility alias; deprecated Google/Bing ping endpoints are never called."""
        return self.check_sitemap()["available"]
