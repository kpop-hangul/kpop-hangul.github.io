"""A read-only, bounded Pages check. HTTP fetches never execute page scripts or ads."""
import hashlib
import os
import re
import subprocess
import time
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.parse import quote, unquote, urljoin, urlsplit

import requests


class PageImages(HTMLParser):
    def __init__(self):
        super().__init__()
        self.images = set()
        self.revisions = set()

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "img" and attrs.get("src"):
            self.images.add(attrs["src"])
        if tag == "span" and attrs.get("data-publication-revision"):
            self.revisions.add(attrs["data-publication-revision"])


def github_repository(repo_root):
    """Parse only owner/repository; never return/log a credential-bearing remote."""
    value = subprocess.run(["git", "config", "--get", "remote.origin.url"], cwd=repo_root,
                           capture_output=True, text=True, timeout=5, check=True).stdout.strip()
    match = re.search(r"github\.com[:/]([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+?)(?:\.git)?$", value)
    if not match:
        raise ValueError("GitHub origin repository could not be resolved")
    return "/".join(match.groups())


class DeploymentVerifier:
    def __init__(self, config, repo_root, session=None):
        self.config, self.repo_root = config, repo_root
        self.session = session or requests.Session()

    def check(self, publication):
        checked = datetime.now(timezone.utc).isoformat()
        started = time.monotonic()

        def result(status, message, **extra):
            return {"status": status, "message": message, "checked_at": checked, **extra}

        def get(url, *, api=False, params=None, limit=25 * 1024 * 1024):
            remaining = 25 - (time.monotonic() - started)
            if remaining <= 0:
                raise TimeoutError("Verification time budget reached")
            headers = {"User-Agent": "Blog-Publication-Verifier/1.0", "Cache-Control": "no-cache"}
            if api:
                headers["Accept"] = "application/vnd.github+json"
                token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
                if token:
                    headers["Authorization"] = f"Bearer {token}"
            response = self.session.get(url, params=params, headers=headers,
                                        timeout=min(6, remaining), allow_redirects=False, stream=True)
            try:
                response.raise_for_status()
                if response.status_code != 200:
                    raise ValueError("Expected HTTP 200")
                chunks, size = [], 0
                for part in response.iter_content(65536):
                    size += len(part)
                    if size > limit or time.monotonic() - started > 25:
                        raise ValueError("Verification response exceeded limits")
                    chunks.append(part)
                return b"".join(chunks), response.headers
            finally:
                response.close()

        try:
            sha = publication.get("commit_sha", "")
            if not re.fullmatch(r"[0-9a-f]{40,64}", sha) or not publication.get("pushed_at"):
                return result("pending", "커밋 Push가 아직 확인되지 않았습니다.")
            repository = github_repository(self.repo_root)
            workflow = self.config.get("github", {}).get("pages_workflow", "deploy.yml")
            if not re.fullmatch(r"[A-Za-z0-9_.-]+\.ya?ml", workflow):
                return result("failed", "Pages workflow 설정이 유효하지 않습니다.")
            raw, _ = get(f"https://api.github.com/repos/{repository}/actions/workflows/{workflow}/runs",
                         api=True, params={"head_sha": sha, "per_page": 100}, limit=2 * 1024 * 1024)
            import json
            runs = [r for r in json.loads(raw).get("workflow_runs", []) if r.get("head_sha") == sha]
            if not runs:
                return result("pending", "해당 커밋의 Pages 실행을 기다리고 있습니다.")
            run = max(runs, key=lambda r: (r.get("run_number", 0), r.get("run_attempt", 0)))
            run_url = f"https://github.com/{repository}/actions/runs/{run['id']}"
            if run.get("status") != "completed":
                return result("pending", "GitHub Pages 작업이 진행 중입니다.", run_url=run_url)
            if run.get("conclusion") != "success":
                return result("failed", "GitHub Pages 작업이 성공하지 못했습니다.", run_url=run_url)
            url = publication["url"]
            parsed = urlsplit(url)
            site = urlsplit(self.config.get("site", {}).get("url", ""))
            if parsed.scheme != "https" or not parsed.hostname or parsed.netloc != site.netloc or parsed.username or parsed.password:
                return result("failed", "공개 글 URL이 설정된 HTTPS 사이트와 다릅니다.")
            page, headers = get(url, params={"publication_check": sha}, limit=4 * 1024 * 1024)
            if "text/html" not in headers.get("Content-Type", "").lower():
                return result("pending", "공개 글의 HTML 응답을 기다리고 있습니다.", run_url=run_url)
            parser = PageImages()
            parser.feed(page.decode("utf-8"))
            if publication["revision"] not in parser.revisions:
                return result("pending", "공개 글이 승인된 최신 본문으로 갱신되지 않았습니다.", run_url=run_url)
            rendered = {unquote(urljoin(url, src)) for src in parser.images}
            for asset in publication.get("assets", []):
                asset_url = urljoin(url, asset["url"])
                if unquote(asset_url) not in rendered:
                    return result("pending", "승인된 이미지가 공개 글에 없습니다.", run_url=run_url)
                payload, headers = get(asset_url, params={"publication_check": sha})
                if not headers.get("Content-Type", "").lower().startswith("image/") or hashlib.sha256(payload).hexdigest() != asset["sha256"]:
                    return result("pending", "공개 이미지가 승인된 파일과 일치하지 않습니다.", run_url=run_url)
            return result("verified", "해당 커밋의 Pages 성공, 공개 본문과 이미지 파일을 확인했습니다.",
                          run_url=run_url, commit_sha=sha, asset_count=len(publication.get("assets", [])))
        except Exception as exc:
            # Exception strings can contain URL credentials; return a safe class name only.
            return result("pending", f"공개 배포 확인을 다시 시도해야 합니다 ({type(exc).__name__}).")
