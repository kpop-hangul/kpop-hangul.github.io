import os
import re
import time
import yaml
import subprocess
from datetime import datetime
from typing import Dict, Any

class GitHubPublisher:
    """
    최종 승인된 아티클을 Astro Content Collection 마크다운 파일로 생성하고
    Git Commit & Push를 통해 GitHub Pages 자동 배포를 트리거하는 모듈
    """

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.repo_root = config.get("github", {}).get("repo_root", "../")
        self.content_dir = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", config.get("github", {}).get("blog_content_dir", "../blog-frontend/src/content/blog"))
        )
        self.auto_commit = config.get("github", {}).get("auto_git_commit", True)
        self.auto_push = config.get("github", {}).get("auto_git_push", False)

        os.makedirs(self.content_dir, exist_ok=True)

    def generate_slug(self, title: str, category: str = "general") -> str:
        """
        GitHub Pages 404 방지를 위해 영문 및 날짜 기반의 깔끔한 URL 슬러그 생성
        """
        today_str = datetime.now().strftime("%Y-%m-%d")
        # 영문/숫자 단어 추출
        ascii_words = re.findall(r"[a-zA-Z0-9]+", title.lower())
        if ascii_words:
            keyword_slug = "-".join(ascii_words[:4])
        else:
            cat_slug = "ai-tips" if "ai" in category.lower() else ("dev-tips" if "개발" in category else "passive-income")
            keyword_slug = f"{cat_slug}-{int(time.time()) % 10000}"

        return f"{today_str}-{keyword_slug}"

    def publish_article(self, article: Dict[str, Any]) -> str:
        """
        승인된 아티클 딕셔너리를 마크다운(.md) 파일로 저장하고 Git 커밋
        """
        title = article.get("title", "무제")
        category = article.get("category", "General")
        slug = self.generate_slug(title, category)
        filepath = os.path.join(self.content_dir, f"{slug}.md")

        frontmatter_data = {
            "title": title,
            "description": article.get("description", ""),
            "pubDate": datetime.now().strftime("%Y-%m-%d"),
            "category": category,
            "tags": article.get("tags", []),
            "author": article.get("author", "앱시안 (absian)"),
            "readingTime": article.get("readingTime", "5 min read"),
            "featured": article.get("featured", False),
            "draft": False,
        }

        if "faqs" in article and article["faqs"]:
            frontmatter_data["faqs"] = article["faqs"]

        # YAML Frontmatter 직렬화
        yaml_content = yaml.dump(
            frontmatter_data,
            allow_unicode=True,
            default_flow_style=False,
            sort_keys=False
        )

        full_content = f"---\n{yaml_content}---\n\n{article.get('markdown_content', '')}\n"

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(full_content)

        print(f"📄 마크다운 아티클 생성 완료: {filepath}")

        # Git Auto Commit & Push (선택 옵션)
        if self.auto_commit:
            self._git_commit_and_push(filepath, title)

        return filepath

    def update_existing_article(self, slug: str, article: Dict[str, Any], new_slug: str = None) -> tuple[str, str]:
        """
        기존 슬러그의 마크다운(.md) 파일을 수정된 내용으로 덮어쓰거나 URL(슬러그)을 변경하고 Git 커밋 & Push
        반환값: (저장된 파일 경로, 최종 슬러그)
        """
        old_filepath = os.path.join(self.content_dir, f"{slug}.md")
        if not os.path.exists(old_filepath):
            matched = [f for f in os.listdir(self.content_dir) if f.startswith(slug) and f.endswith(".md")]
            if matched:
                old_filepath = os.path.join(self.content_dir, matched[0])
                slug = os.path.splitext(matched[0])[0]
            else:
                raise FileNotFoundError(f"수정할 게시글 파일을 찾을 수 없습니다: {slug}.md")

        final_slug = slug
        if new_slug:
            clean_new_slug = re.sub(r"[^a-zA-Z0-9\-_]", "", new_slug.strip().lower())
            if clean_new_slug and clean_new_slug != slug:
                final_slug = clean_new_slug

        new_filepath = os.path.join(self.content_dir, f"{final_slug}.md")

        title = article.get("title", "무제")
        category = article.get("category", "General")
        pub_date = article.get("pubDate") or datetime.now().strftime("%Y-%m-%d")

        frontmatter_data = {
            "title": title,
            "description": article.get("description", ""),
            "pubDate": pub_date,
            "category": category,
            "tags": article.get("tags", []),
            "author": article.get("author", "앱시안 (absian)"),
            "readingTime": article.get("readingTime", "5 min read"),
            "featured": article.get("featured", False),
            "draft": False,
        }

        if "faqs" in article and article["faqs"]:
            frontmatter_data["faqs"] = article["faqs"]

        yaml_content = yaml.dump(
            frontmatter_data,
            allow_unicode=True,
            default_flow_style=False,
            sort_keys=False
        )

        full_content = f"---\n{yaml_content}---\n\n{article.get('markdown_content', '')}\n"

        with open(new_filepath, "w", encoding="utf-8") as f:
            f.write(full_content)

        # 슬러그(URL)가 변경된 경우 이전 파일 삭제
        is_renamed = (old_filepath != new_filepath)
        if is_renamed and os.path.exists(old_filepath):
            try:
                os.remove(old_filepath)
                print(f"🗑️ 이전 파일 삭제 완료: {old_filepath}")
            except Exception as e:
                print(f"⚠️ 이전 파일 삭제 실패: {e}")

        print(f"📄 마크다운 아티클 수정 완료: {new_filepath} (슬러그: {final_slug})")

        if self.auto_commit:
            try:
                if is_renamed:
                    subprocess.run(["git", "add", "-A"], cwd=self.repo_root, check=False)
                    commit_msg = f"fix(blog): rename/update post from {slug} to {final_slug}"
                else:
                    subprocess.run(["git", "add", new_filepath], cwd=self.repo_root, check=False)
                    commit_msg = f"fix(blog): update post - {title[:30]}"

                subprocess.run(["git", "commit", "-m", commit_msg], cwd=self.repo_root, check=False)
                if self.auto_push:
                    subprocess.run(["git", "push", "origin", "main"], cwd=self.repo_root, check=False)
            except Exception as e:
                print(f"[GitHubPublisher] Git 작업 중 알림: {e}")

        return new_filepath, final_slug

    def _git_commit_and_push(self, filepath: str, title: str):
        """Git 커밋 및 Push 실행"""
        try:
            subprocess.run(["git", "add", filepath], cwd=self.repo_root, check=False)
            commit_msg = f"feat(blog): publish new post - {title[:30]}"
            subprocess.run(["git", "commit", "-m", commit_msg], cwd=self.repo_root, check=False)
            if self.auto_push:
                print("🚀 GitHub 원격 저장소로 Push 실행 중...")
                subprocess.run(["git", "push", "origin", "main"], cwd=self.repo_root, check=False)
        except Exception as e:
            print(f"[GitHubPublisher] Git 작업 중 알림: {e}")
