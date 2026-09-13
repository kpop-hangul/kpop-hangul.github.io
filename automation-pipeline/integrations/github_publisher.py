import os
import re
import time
import yaml
import subprocess
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Tuple, Optional

class GitHubPublisher:
    """
    최종 승인된 아티클을 Astro Content Collection 마크다운 파일로 생성하고
    고해상도 SVG 썸네일 및 본문 설명 다이어그램과 함께 Git 커밋을 수행하는 모듈
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
        GitHub Pages 404 방지를 위해 아티스트/곡명/영문 기반의 고유한 URL 슬러그 생성
        """
        today_str = datetime.now().strftime("%Y-%m-%d")
        ascii_words = re.findall(r"[a-zA-Z0-9]+", title.lower())
        meaningful_words = [w for w in ascii_words if not w.isdigit() or len(w) > 2]

        if len(meaningful_words) >= 2:
            keyword_slug = "-".join(meaningful_words[:4])
        else:
            h = hashlib.md5(title.encode()).hexdigest()[:6]
            if ascii_words:
                keyword_slug = f"{'-'.join(ascii_words[:2])}-{h}"
            else:
                cat_slug = "kpop-lesson" if "kpop" in category.lower() else "song-lesson"
                keyword_slug = f"{cat_slug}-{h}"

        return f"{today_str}-{keyword_slug}"

    def publish_article(self, article: Dict[str, Any]) -> str:
        """
        승인된 아티클 딕셔너리를 썸네일 및 본문 이미지와 함께 마크다운(.md) 파일로 저장하고 Git 커밋
        """
        title = article.get("title", "Learn Korean with K-Pop")
        category = article.get("category", "Beginner (Level 1)")
        slug = article.get("slug") or self.generate_slug(title, category)
        filepath = os.path.join(self.content_dir, f"{slug}.md")

        # 1. 고해상도 SVG 썸네일 생성 및 heroImage 설정
        if "heroImage" not in article or not article["heroImage"] or article["heroImage"] == "/images/default-hero.svg":
            try:
                from modules.thumbnail_generator import generate_thumbnail_for_post
                post_data = {
                    "slug": slug,
                    "title": title,
                    "artist": article.get("artist", "K-Pop Artist"),
                    "songTitle": article.get("songTitle", ""),
                    "hangulTitle": article.get("hangulTitle", ""),
                    "difficulty": article.get("difficulty", "Beginner"),
                    "genre": article.get("genre", "Dance & Pop"),
                    "chartRank": article.get("chartRank"),
                    "chartSource": article.get("chartSource", "Melon Top 100")
                }
                article["heroImage"] = generate_thumbnail_for_post(post_data)
            except Exception as e:
                print(f"[GitHubPublisher] 썸네일 생성 예외: {e}")
                article["heroImage"] = f"/images/thumbnails/{slug}.svg"

        # 2. 본문 설명 이해용 다이어그램 2종 자동 생성 및 본문 삽입
        try:
            from modules.article_image_generator import generate_and_integrate_article_images
            updated_content, imgs = generate_and_integrate_article_images(article, slug)
            article["markdown_content"] = updated_content
        except Exception as e:
            print(f"[GitHubPublisher] 본문 다이어그램 생성 예외: {e}")

        frontmatter_data = {
            "title": title,
            "description": article.get("description", ""),
            "pubDate": article.get("pubDate") or datetime.now().strftime("%Y-%m-%d"),
            "heroImage": article.get("heroImage", f"/images/thumbnails/{slug}.svg"),
            "category": category,
            "difficulty": article.get("difficulty", "Beginner"),
            "genre": article.get("genre", "Dance & Pop"),
            "artist": article.get("artist", "Various Artists"),
            "songTitle": article.get("songTitle", ""),
            "hangulTitle": article.get("hangulTitle", ""),
            "album": article.get("album", ""),
            "chartRank": article.get("chartRank", 1),
            "chartSource": article.get("chartSource", "Melon Top 100"),
            "tags": article.get("tags", []),
            "author": article.get("author", "K-Pop Hangul Team"),
            "readingTime": article.get("readingTime", "6 min read"),
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

        # Git Auto Commit
        if self.auto_commit:
            self._git_commit_and_push(filepath, title, slug=slug)

        return filepath

    def update_existing_article(self, slug: str, article: Dict[str, Any], new_slug: str = None) -> Tuple[str, str]:
        """
        기존 슬러그의 마크다운(.md) 파일을 수정된 내용으로 덮어쓰거나 URL(슬러그)을 변경하고 Git 커밋
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

        title = article.get("title", "Learn Korean with K-Pop")
        category = article.get("category", "Beginner (Level 1)")
        pub_date = article.get("pubDate") or datetime.now().strftime("%Y-%m-%d")

        # 썸네일 & 다이어그램 보완
        if "heroImage" not in article or not article["heroImage"] or article["heroImage"] == "/images/default-hero.svg":
            try:
                from modules.thumbnail_generator import generate_thumbnail_for_post
                post_data = {
                    "slug": final_slug,
                    "title": title,
                    "artist": article.get("artist", "K-Pop Artist"),
                    "songTitle": article.get("songTitle", ""),
                    "hangulTitle": article.get("hangulTitle", ""),
                    "difficulty": article.get("difficulty", "Beginner"),
                    "genre": article.get("genre", "Dance & Pop"),
                    "chartRank": article.get("chartRank"),
                    "chartSource": article.get("chartSource", "Melon Top 100")
                }
                article["heroImage"] = generate_thumbnail_for_post(post_data)
            except Exception:
                article["heroImage"] = f"/images/thumbnails/{final_slug}.svg"

        frontmatter_data = {
            "title": title,
            "description": article.get("description", ""),
            "pubDate": pub_date,
            "updatedDate": datetime.now().strftime("%Y-%m-%d"),
            "heroImage": article.get("heroImage", f"/images/thumbnails/{final_slug}.svg"),
            "category": category,
            "difficulty": article.get("difficulty", "Beginner"),
            "genre": article.get("genre", "Dance & Pop"),
            "artist": article.get("artist", "Various Artists"),
            "songTitle": article.get("songTitle", ""),
            "hangulTitle": article.get("hangulTitle", ""),
            "album": article.get("album", ""),
            "chartRank": article.get("chartRank", 1),
            "chartSource": article.get("chartSource", "Melon Top 100"),
            "tags": article.get("tags", []),
            "author": article.get("author", "K-Pop Hangul Team"),
            "readingTime": article.get("readingTime", "6 min read"),
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

        is_renamed = (old_filepath != new_filepath)
        if is_renamed and os.path.exists(old_filepath):
            try:
                os.remove(old_filepath)
                print(f"🗑️ 이전 파일 삭제 완료: {old_filepath}")
            except Exception as e:
                print(f"⚠️ 이전 파일 삭제 실패: {e}")

        print(f"📄 마크다운 아티클 수정 완료: {new_filepath} (슬러그: {final_slug})")

        if self.auto_commit:
            paths = [new_filepath]
            if is_renamed:
                paths.append(old_filepath)
            self._commit_paths(paths, f"fix(blog): update post - {title[:40]}", slug=final_slug)

        return new_filepath, final_slug

    def _git_commit_and_push(self, filepath: str, title: str, slug: Optional[str] = None):
        """Git 커밋 실행 (썸네일 및 본문 이미지 자동 포함)"""
        self._commit_paths([filepath], f"feat(blog): publish new post - {title[:40]}", slug=slug)

    def _commit_paths(self, paths: list, message: str, slug: Optional[str] = None):
        try:
            full_paths = list(paths)
            if slug:
                thumb_path = Path(self.repo_root) / f"blog-frontend/public/images/thumbnails/{slug}.svg"
                if thumb_path.exists():
                    full_paths.append(str(thumb_path))
                article_img_dir = Path(self.repo_root) / "blog-frontend/public/images/articles"
                if article_img_dir.exists():
                    for img_file in article_img_dir.glob(f"*{slug}*"):
                        full_paths.append(str(img_file))

            for p in full_paths:
                subprocess.run(["git", "add", p], cwd=self.repo_root, check=False)

            subprocess.run(["git", "commit", "-m", message], cwd=self.repo_root, check=False)

            if self.auto_push:
                print("🚀 GitHub 원격 저장소로 Push 실행 중...")
                subprocess.run(["git", "push", "origin", "main"], cwd=self.repo_root, check=False)
        except Exception as e:
            print(f"[GitHubPublisher] Git 작업 중 알림: {e}")
