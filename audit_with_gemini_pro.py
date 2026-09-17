#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Audits K-Pop Hangul Blog using GPT high reasoning via AntigravityRunner.
Inspects Frontend Code, Design, Pedagogical Content Structure, and Pipeline.
"""

import os
import sys
import json

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(SCRIPT_DIR, "automation-pipeline"))

from integrations.antigravity_runner import AntigravityRunner


def read_file_snippet(path: str, max_lines: int = 800) -> str:
    full_path = os.path.join(SCRIPT_DIR, path)
    if not os.path.exists(full_path):
        return f"[File {path} not found]"
    try:
        with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
            return "".join(lines[:max_lines])
    except Exception as e:
        return f"[Error reading {path}: {e}]"


def main():
    config = {"blogId": "kpop-hangul"}
    runner = AntigravityRunner(config)

    print("🧐 [Audit] Gathering key files for GPT high reasoning review...")

    files_to_inspect = {
        "BaseLayout.astro": "blog-frontend/src/layouts/BaseLayout.astro",
        "BlogPostLayout.astro": "blog-frontend/src/layouts/BlogPostLayout.astro",
        "Header.astro": "blog-frontend/src/components/Header.astro",
        "Footer.astro": "blog-frontend/src/components/Footer.astro",
        "Card.astro": "blog-frontend/src/components/Card.astro",
        "SEO.astro": "blog-frontend/src/components/SEO.astro",
        "AdSense.astro": "blog-frontend/src/components/AdSense.astro",
        "index.astro": "blog-frontend/src/pages/index.astro",
        "hangul/index.astro": "blog-frontend/src/pages/hangul/index.astro",
        "about.astro": "blog-frontend/src/pages/about.astro",
        "contact.astro": "blog-frontend/src/pages/contact.astro",
        "gallery.astro": "blog-frontend/src/pages/gallery.astro",
        "difficulty/[level].astro": "blog-frontend/src/pages/difficulty/[level].astro",
        "artists/[artist].astro": "blog-frontend/src/pages/artists/[artist].astro",
        "genres/[genre].astro": "blog-frontend/src/pages/genres/[genre].astro",
        "kpop.ts": "blog-frontend/src/utils/kpop.ts",
        "slug.ts": "blog-frontend/src/utils/slug.ts",
        "config.ts": "blog-frontend/src/content/config.ts",
        "Sample Post (RESCENE)": "blog-frontend/src/content/blog/2026-09-08-rescene-love-attack.md",
        "thumbnail_generator.py": "automation-pipeline/modules/thumbnail_generator.py",
        "article_image_generator.py": "automation-pipeline/modules/article_image_generator.py",
        "github_publisher.py": "automation-pipeline/integrations/github_publisher.py",
        "kpop_chart_crawler.py": "automation-pipeline/modules/kpop_chart_crawler.py",
        "content_writer.py": "automation-pipeline/agents/content_writer.py",
        "manage_kpop.py": "automation-pipeline/manage_kpop.py",
    }

    gathered_content = []
    for label, rel_path in files_to_inspect.items():
        snippet = read_file_snippet(rel_path)
        gathered_content.append(f"=== FILE: {label} ({rel_path}) ===\n{snippet}\n")

    full_source_bundle = "\n\n".join(gathered_content)

    system_prompt = """You are a Principal Frontend Architect, UI/UX Design Director, and Master Korean Language Educator.
You are conducting a strict, uncompromising design, code, and pedagogical audit of 'K-Pop Hangul' (Learn Korean with K-Pop Hits from Melon & Spotify).

[Audit Dimensions]
1. Code Correctness & Architecture:
   - TypeScript/Astro schema alignment, broken imports, hardcoded legacy strings from old templates (e.g. references to '앱시안' or Korean tech blog terms in English layout).
   - Clean separation of concerns, 404 safety for dynamic routes.
2. UI/UX & Visual Design:
   - Color harmony (K-Pop vibe: indigo/violet/pink accents), typography for Hangul readability, contrast, mobile layout responsiveness.
   - AdSense component handling (when user excludes ads, it should not render empty boxes or hardcoded third-party pub-IDs).
3. Korean Learning Pedagogical Effectiveness:
   - Is the 3-line format (Hangul -> Romanization -> English) crystal clear?
   - Are vocabulary and grammar sections easy to study on mobile?
   - Any missing essential features for language learners (e.g., Pronunciation guide, Hangul study guide page, copy buttons)?
4. Automation Pipeline Reliability:
   - Chart crawler resilience for Melon Top 100 & Spotify Daily.
   - Daily 3-song generation stability and data recording.

[Required Output Format - JSON]
{
  "overall_score": 92,
  "summary": "High-level 3-sentence evaluation of current state.",
  "critical_fixes": [
    {
      "file": "path/to/file",
      "issue": "Description of defect or legacy artifact",
      "recommendation": "Concrete fix instruction"
    }
  ],
  "design_enhancements": [
    {
      "component": "Component name",
      "enhancement": "UI/UX upgrade recommendation"
    }
  ],
  "pedagogical_enhancements": [
    {
      "topic": "Feature or content enhancement",
      "recommendation": "How to make the learning experience even better"
    }
  ]
}
"""

    user_prompt = f"""Please review the following complete codebase and design bundle for K-Pop Hangul:

{full_source_bundle}

Provide your detailed, expert audit in strict JSON format.
"""

    print("🤖 [Audit] Invoking GPT high reasoning (Thinking Effort: High)...")
    result = runner.generate_text(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        model_name="gpt-6-astra",
        effort="high"
    )

    if result:
        print("\n" + "=" * 70)
        print(" 🎯  GPT high reasoning Audit Report Received:")
        print("=" * 70)
        print(result)
        with open(os.path.join(SCRIPT_DIR, "gpt_audit_report.json"), "w", encoding="utf-8") as f:
            f.write(result)
    else:
        print("⚠️ No output received from GPT high reasoning.")


if __name__ == "__main__":
    main()
