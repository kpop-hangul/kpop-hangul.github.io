"""Save reviewed articles and propagate Git failures to the approval queue."""
import os
import re
import time
from pathlib import Path
from datetime import datetime
import subprocess
import yaml
from modules.gpt_images import referenced_assets, image_identity
from modules.content_validation import validate_article, ContentValidationError, body_fingerprint


class GitHubPublisher:
    def __init__(self, config):
        self.config = config
        pipeline_root = Path(__file__).resolve().parents[1]
        self.repo_root = str((pipeline_root / config.get("github", {}).get("repo_root", "../")).resolve())
        self.content_dir = str((pipeline_root / config.get("github", {}).get("blog_content_dir", "../blog-frontend/src/content/blog")).resolve())
        self.auto_commit = config.get("github", {}).get("auto_git_commit", True)
        self.auto_push = config.get("github", {}).get("auto_git_push", False)

    def generate_slug(self, title, category="general"):
        words = re.findall(r"[a-zA-Z0-9]+", title.lower())
        meaningful_words = [w for w in words if not w.isdigit() or len(w) > 2]
        if len(meaningful_words) >= 2:
            keyword = "-".join(words[:4])
        else:
            import hashlib
            h = hashlib.md5(title.encode()).hexdigest()[:6]
            if words:
                keyword = f"{'-'.join(words[:2])}-{h}"
            else:
                keyword = f"post-{h}"
        return f"{datetime.now():%Y-%m-%d}-{keyword}"

    def _path(self, slug):
        if not isinstance(slug, str) or not re.fullmatch(r"[a-zA-Z0-9가-힣_-]+", slug):
            raise ValueError("유효하지 않은 게시글 슬러그")
        return Path(self.content_dir) / f"{slug}.md"

    @staticmethod
    def _read_post(path):
        text = path.read_text(encoding="utf-8")
        match = re.match(r"\A---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|$)(.*)\Z", text, re.DOTALL)
        if match:
            metadata = yaml.safe_load(match.group(1))
            return metadata if isinstance(metadata, dict) else {}, match.group(2)
        return {}, text

    def _validate_for_publication(self, article, human_approved, existing_path=None):
        if human_approved is not True:
            raise PermissionError("구체적인 초안 본문과 출처에 대한 사람의 승인이 필요합니다.")
        validate_article(article)
        generation = article.get("image_generation")
        if generation and (generation.get("status") != "complete" or generation.get("content_identity") != image_identity(article)):
            raise ContentValidationError("본문이 바뀌었거나 이미지 생성이 미완료입니다. 이미지를 다시 생성하고 검토하세요.")
        if self.auto_commit:
            referenced_assets(article, Path(self.repo_root) / "blog-frontend/public")
        fingerprint = body_fingerprint(article["markdown_content"])
        if not fingerprint:
            raise ContentValidationError("본문이 비어 있습니다.")
        # Exact duplicate-body detection is deliberately limited; it is not a semantic/factual audit.
        for path in Path(self.content_dir).glob("*.md"):
            if path == existing_path:
                continue
            _, body = self._read_post(path)
            if body_fingerprint(body) == fingerprint:
                raise ContentValidationError(f"기존 글과 본문이 같습니다: {path.name}")

    def _metadata(self, article, existing=None):
        data = dict(existing or {})
        data.update({"title": article["title"], "description": article["description"],
                     "category": article["category"], "tags": article.get("tags", []),
                     "pubDate": data.get("pubDate") or article.get("pubDate") or datetime.now().strftime("%Y-%m-%d"),
                     "author": article.get("author") or data.get("author") or self.config.get("site", {}).get("author", "편집팀"),
                     "readingTime": article.get("readingTime", "5 min read"),
                     "featured": article.get("featured", data.get("featured", False)),
                     "draft": False, "faqs": article.get("faqs", [])})
        for key in ("heroImage", "summaryCards"):
            if key in article:
                data[key] = article[key]
        for key in ("difficulty", "genre", "artist", "songTitle", "hangulTitle", "album", "chartRank", "chartSource", "youtubeId"):
            if key in article:
                data[key] = article[key]
        if existing is not None:
            data["updatedDate"] = datetime.now().strftime("%Y-%m-%d")
            data.pop("reviewStatus", None)
            data.pop("reviewReason", None)
        return data

    def publish_article(self, article, pre_commit_hook=None, *, human_approved=False):
        self._validate_for_publication(article, human_approved)
        slug = article.get("slug") or self.generate_slug(article["title"], article["category"])
        path = self._path(slug)
        if path.exists():
            raise FileExistsError(f"이미 있는 슬러그입니다. 기존 글 수정 경로를 사용하세요: {slug}")
        path.parent.mkdir(parents=True, exist_ok=True)
        self._save(path, article, self._metadata(article))
        if self.auto_commit:
            self._git_commit_and_push(str(path), article["title"], slug=slug, article=article)
        # A failed Git operation must not mark a keyword as published.
        if pre_commit_hook:
            pre_commit_hook(slug)
        return str(path)

    def update_existing_article(self, slug, article, new_slug=None, *, human_approved=False):
        old_path = self._path(slug)
        if not old_path.exists():
            raise FileNotFoundError(f"수정할 게시글이 없습니다: {slug}")
        self._validate_for_publication(article, human_approved, existing_path=old_path)
        final_slug = new_slug or slug
        new_path = self._path(final_slug)
        if new_path != old_path and new_path.exists():
            raise FileExistsError(f"대상 슬러그가 이미 있습니다: {final_slug}")
        existing, _ = self._read_post(old_path)
        self._save(new_path, article, self._metadata(article, existing))
        if new_path != old_path:
            old_path.unlink()
        if self.auto_commit:
            paths = [str(new_path)] + ([str(old_path)] if old_path != new_path else [])
            paths.extend(referenced_assets(article, Path(self.repo_root) / "blog-frontend/public"))
            self._commit_paths(paths, f"fix(blog): update post - {article['title'][:60]}")
        return str(new_path), final_slug

    def delete_article(self, slug, *, human_approved=False):
        if human_approved is not True:
            raise PermissionError("글 삭제는 사람의 명시적 승인이 필요합니다.")
        path = self._path(slug)
        if not path.is_file():
            raise FileNotFoundError(f"정확한 게시글 슬러그가 필요합니다: {slug}")
        meta, body = self._read_post(path)
        # Assets may be referenced by another post or queued draft. Keep them until a separate audit.
        path.unlink()
        if self.auto_commit:
            self._commit_paths([str(path)], f"fix(blog): delete post - {meta.get('title', slug)[:60]}")
        return meta.get("title", slug)

    @staticmethod
    def _save(path, article, metadata):
        validate_article({**metadata, "markdown_content": article["markdown_content"]})
        frontmatter = yaml.safe_dump(metadata, allow_unicode=True, sort_keys=False)
        path.write_text(f"---\n{frontmatter}---\n\n{article['markdown_content']}\n", encoding="utf-8")

    def _git_commit_and_push(self, filepath, title, slug=None, article=None):
        if article is None:
            meta, body = self._read_post(Path(filepath))
            article = {**meta, "markdown_content": body}
        paths = [filepath] + referenced_assets(article, Path(self.repo_root) / "blog-frontend/public")
        self._commit_paths(paths, f"feat(blog): publish new post - {title[:60]}")

    def _commit_paths(self, paths, message):
        # No broad `git add -A`, ignored errors, or automatic history rewrite.
        subprocess.run(["git", "add", "--", *paths], cwd=self.repo_root, check=True)
        diff = subprocess.run(["git", "diff", "--cached", "--quiet", "--", *paths], cwd=self.repo_root)
        if diff.returncode == 1:
            subprocess.run(["git", "commit", "--only", "-m", message, "--", *paths], cwd=self.repo_root, check=True)
        elif diff.returncode != 0:
            raise RuntimeError("Git 변경 확인 실패")
        if self.auto_push:
            subprocess.run(["git", "push", "origin", "HEAD:main"], cwd=self.repo_root, check=True)
