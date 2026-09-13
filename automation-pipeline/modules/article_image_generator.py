"""
K-Pop Hangul Blog Contextual Article Illustration Generator
Generates high-resolution 1536x1024 educational infographic diagrams for K-Pop song lessons:
- Image 1: Lyrics Breakdown, Syllable Anatomy & Phonetic Linking Rules (연음/음운 변동)
- Image 2: Essential Grammar Formulas, Sentence Patterns & Conversational Nuance
Converts SVG to WebP via ffmpeg and automatically injects standard Astro figure blocks into markdown.
"""
import os
import re
import subprocess
from html import escape
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional

BASE_DIR = Path(__file__).resolve().parents[2]
PUBLIC_IMG_DIR = BASE_DIR / "blog-frontend" / "public" / "images" / "articles"
DIST_IMG_DIR = BASE_DIR / "blog-frontend" / "dist" / "images" / "articles"

SITE_PREFIX = "kpop"


def clean_text(text: str, max_len: int = 40) -> str:
    text = re.sub(r"[#*`_~]", "", str(text)).strip()
    return text[:max_len] + ("..." if len(text) > max_len else "")


def extract_h2_sections(markdown_content: str) -> List[Tuple[str, str]]:
    """Extracts H2 headings and initial sample sentences from markdown content."""
    sections = []
    lines = markdown_content.splitlines()
    curr_h2 = None
    curr_body = []

    for line in lines:
        if line.strip().startswith("## "):
            if curr_h2:
                body_sample = " ".join(curr_body).strip()
                sections.append((curr_h2, body_sample))
            curr_h2 = line.strip()
            curr_body = []
        elif curr_h2 and line.strip() and not line.strip().startswith("#") and not line.strip().startswith("<!--"):
            if len(curr_body) < 3:
                curr_body.append(line.strip())

    if curr_h2:
        body_sample = " ".join(curr_body).strip()
        sections.append((curr_h2, body_sample))

    return sections


def generate_lyrics_phonetics_svg(
    song_title: str,
    artist: str,
    difficulty: str,
    genre: str,
    cards: List[Dict[str, str]]
) -> str:
    """Creates a 1536x1024 educational SVG for Chorus Lyrics & Sound Change Rules."""
    accent = "#38bdf8" if "inter" in difficulty.lower() else ("#f43f5e" if "adv" in difficulty.lower() else "#2dd4bf")
    badge_color = "#818cf8" if "inter" in difficulty.lower() else ("#fb7185" if "adv" in difficulty.lower() else "#34d399")

    # 3 Cards Layout
    cards_svg = ""
    card_width = 410
    card_height = 500
    start_x = 98
    card_y = 310

    for idx, item in enumerate(cards[:3]):
        cx = start_x + idx * (card_width + 44)
        num_str = f"0{idx + 1}"
        item_title = escape(clean_text(item.get("title", f"Point {idx + 1}"), 22))
        item_badge = escape(clean_text(item.get("badge", "KEY RULE"), 18))
        desc1 = escape(clean_text(item.get("desc1", "Hangul Syllable Block"), 32))
        desc2 = escape(clean_text(item.get("desc2", "Phonetic Linking Rule"), 32))
        desc3 = escape(clean_text(item.get("desc3", "Lyric Pronunciation"), 32))
        highlight = escape(clean_text(item.get("highlight", "Must Know"), 25))

        cards_svg += f"""
    <!-- Card {idx + 1} -->
    <g transform="translate({cx}, {card_y})">
      <rect width="{card_width}" height="{card_height}" rx="24" fill="#0f172a" fill-opacity="0.92" stroke="{accent}" stroke-width="1.8" />
      
      <!-- Card Top Badge -->
      <rect x="28" y="28" width="130" height="32" rx="16" fill="{accent}" fill-opacity="0.18" stroke="{accent}" stroke-width="1" />
      <text x="93" y="49" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif" font-size="13" font-weight="800" fill="{badge_color}" text-anchor="middle">{item_badge}</text>
      <text x="{card_width - 32}" y="52" font-family="'Segoe UI', Roboto, sans-serif" font-size="28" font-weight="900" fill="{accent}" opacity="0.4" text-anchor="end">{num_str}</text>

      <!-- Card Title -->
      <text x="28" y="112" font-family="-apple-system, BlinkMacSystemFont, 'Pretendard', sans-serif" font-size="24" font-weight="800" fill="#ffffff">{item_title}</text>
      <line x1="28" y1="132" x2="{card_width - 28}" y2="132" stroke="#334155" stroke-width="1.5" />

      <!-- Step Details -->
      <g transform="translate(28, 165)">
        <circle cx="10" cy="10" r="4" fill="{accent}" />
        <text x="26" y="16" font-family="-apple-system, BlinkMacSystemFont, 'Pretendard', sans-serif" font-size="18" font-weight="500" fill="#cbd5e1">{desc1}</text>
      </g>

      <g transform="translate(28, 230)">
        <circle cx="10" cy="10" r="4" fill="{accent}" />
        <text x="26" y="16" font-family="-apple-system, BlinkMacSystemFont, 'Pretendard', sans-serif" font-size="18" font-weight="500" fill="#cbd5e1">{desc2}</text>
      </g>

      <g transform="translate(28, 295)">
        <circle cx="10" cy="10" r="4" fill="{accent}" />
        <text x="26" y="16" font-family="-apple-system, BlinkMacSystemFont, 'Pretendard', sans-serif" font-size="18" font-weight="500" fill="#cbd5e1">{desc3}</text>
      </g>

      <!-- Bottom Highlight Box -->
      <rect x="28" y="380" width="{card_width - 56}" height="84" rx="16" fill="#1e293b" fill-opacity="0.8" stroke="#475569" stroke-width="1" />
      <text x="44" y="414" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif" font-size="12" font-weight="700" fill="{badge_color}" letter-spacing="1">TAKEAWAY</text>
      <text x="44" y="444" font-family="-apple-system, BlinkMacSystemFont, 'Pretendard', sans-serif" font-size="17" font-weight="700" fill="#f8fafc">{highlight}</text>
    </g>
"""

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1536 1024" width="1536" height="1024">
  <defs>
    <linearGradient id="bgArtGrad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#090d16" />
      <stop offset="50%" stop-color="#0f172a" />
      <stop offset="100%" stop-color="#1e1b4b" />
    </linearGradient>
    <radialGradient id="glowArt" cx="80%" cy="20%" r="50%">
      <stop offset="0%" stop-color="{accent}" stop-opacity="0.25" />
      <stop offset="100%" stop-color="{accent}" stop-opacity="0" />
    </radialGradient>
  </defs>

  <!-- Background Canvas -->
  <rect width="1536" height="1024" fill="url(#bgArtGrad)" />
  <rect width="1536" height="1024" fill="url(#glowArt)" />

  <!-- Decorative Top Banner -->
  <g transform="translate(98, 70)">
    <rect width="360" height="40" rx="20" fill="{accent}" fill-opacity="0.15" stroke="{accent}" stroke-width="1.5" />
    <circle cx="24" cy="20" r="6" fill="{accent}" />
    <text x="42" y="26" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif" font-size="15" font-weight="800" fill="#ffffff" letter-spacing="1">K-POP HANGUL MASTER GUIDE 01</text>
  </g>

  <!-- Headline -->
  <g transform="translate(98, 160)">
    <text x="0" y="0" font-family="-apple-system, BlinkMacSystemFont, 'Pretendard', sans-serif" font-size="44" font-weight="900" fill="#ffffff" letter-spacing="-1">
      {escape(clean_text(artist, 25))} - '{escape(clean_text(song_title, 25))}' Lyrics &amp; Sound Rules
    </text>
    <text x="0" y="44" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif" font-size="22" font-weight="500" fill="#94a3b8">
      Syllable Block Construction • Phonetic Liaison (연음) • Natural Chorus Pronunciation
    </text>
  </g>

  <!-- Central Cards -->
  {cards_svg}

  <!-- Footer Bar -->
  <g transform="translate(98, 880)">
    <rect width="1340" height="56" rx="16" fill="#090d16" fill-opacity="0.95" stroke="#334155" stroke-width="1.5" />
    <circle cx="28" cy="28" r="6" fill="{accent}" />
    <text x="48" y="34" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif" font-size="18" font-weight="700" fill="#fde68a">
      National Institute of Korean Language (국립국어원) Revised Standards
    </text>
    <text x="640" y="34" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif" font-size="16" font-weight="500" fill="#94a3b8">
      | Pedagogical Diagram for Global K-Pop Korean Learners
    </text>
    <text x="1310" y="34" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif" font-size="16" font-weight="700" fill="{accent}" text-anchor="end">
      kpop-hangul.github.io
    </text>
  </g>
</svg>"""
    return svg.strip()


def generate_grammar_patterns_svg(
    song_title: str,
    artist: str,
    difficulty: str,
    genre: str,
    cards: List[Dict[str, str]]
) -> str:
    """Creates a 1536x1024 educational SVG for Grammar Deep Dive & Sentence Patterns."""
    accent = "#a855f7" if "inter" in difficulty.lower() else ("#f43f5e" if "adv" in difficulty.lower() else "#38bdf8")
    badge_color = "#c084fc" if "inter" in difficulty.lower() else ("#fb7185" if "adv" in difficulty.lower() else "#67e8f9")

    # 3 Cards Layout
    cards_svg = ""
    card_width = 410
    card_height = 500
    start_x = 98
    card_y = 310

    for idx, item in enumerate(cards[:3]):
        cx = start_x + idx * (card_width + 44)
        num_str = f"0{idx + 1}"
        item_title = escape(clean_text(item.get("title", f"Grammar Formula {idx + 1}"), 22))
        item_badge = escape(clean_text(item.get("badge", "PATTERN"), 18))
        desc1 = escape(clean_text(item.get("desc1", "Base Verb Stem Attachment"), 32))
        desc2 = escape(clean_text(item.get("desc2", "Real Lyric Example Breakdown"), 32))
        desc3 = escape(clean_text(item.get("desc3", "Conversational Nuance (반말/존댓말)"), 32))
        highlight = escape(clean_text(item.get("highlight", "Key Formula"), 25))

        cards_svg += f"""
    <!-- Card {idx + 1} -->
    <g transform="translate({cx}, {card_y})">
      <rect width="{card_width}" height="{card_height}" rx="24" fill="#0f172a" fill-opacity="0.92" stroke="{accent}" stroke-width="1.8" />
      
      <!-- Card Top Badge -->
      <rect x="28" y="28" width="130" height="32" rx="16" fill="{accent}" fill-opacity="0.18" stroke="{accent}" stroke-width="1" />
      <text x="93" y="49" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif" font-size="13" font-weight="800" fill="{badge_color}" text-anchor="middle">{item_badge}</text>
      <text x="{card_width - 32}" y="52" font-family="'Segoe UI', Roboto, sans-serif" font-size="28" font-weight="900" fill="{accent}" opacity="0.4" text-anchor="end">{num_str}</text>

      <!-- Card Title -->
      <text x="28" y="112" font-family="-apple-system, BlinkMacSystemFont, 'Pretendard', sans-serif" font-size="24" font-weight="800" fill="#ffffff">{item_title}</text>
      <line x1="28" y1="132" x2="{card_width - 28}" y2="132" stroke="#334155" stroke-width="1.5" />

      <!-- Step Details -->
      <g transform="translate(28, 165)">
        <circle cx="10" cy="10" r="4" fill="{accent}" />
        <text x="26" y="16" font-family="-apple-system, BlinkMacSystemFont, 'Pretendard', sans-serif" font-size="18" font-weight="500" fill="#cbd5e1">{desc1}</text>
      </g>

      <g transform="translate(28, 230)">
        <circle cx="10" cy="10" r="4" fill="{accent}" />
        <text x="26" y="16" font-family="-apple-system, BlinkMacSystemFont, 'Pretendard', sans-serif" font-size="18" font-weight="500" fill="#cbd5e1">{desc2}</text>
      </g>

      <g transform="translate(28, 295)">
        <circle cx="10" cy="10" r="4" fill="{accent}" />
        <text x="26" y="16" font-family="-apple-system, BlinkMacSystemFont, 'Pretendard', sans-serif" font-size="18" font-weight="500" fill="#cbd5e1">{desc3}</text>
      </g>

      <!-- Bottom Highlight Box -->
      <rect x="28" y="380" width="{card_width - 56}" height="84" rx="16" fill="#1e293b" fill-opacity="0.8" stroke="#475569" stroke-width="1" />
      <text x="44" y="414" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif" font-size="12" font-weight="700" fill="{badge_color}" letter-spacing="1">FORMULA MAP</text>
      <text x="44" y="444" font-family="-apple-system, BlinkMacSystemFont, 'Pretendard', sans-serif" font-size="17" font-weight="700" fill="#f8fafc">{highlight}</text>
    </g>
"""

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1536 1024" width="1536" height="1024">
  <defs>
    <linearGradient id="bgGramGrad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#090514" />
      <stop offset="50%" stop-color="#1e1b4b" />
      <stop offset="100%" stop-color="#0a0f1d" />
    </linearGradient>
    <radialGradient id="glowGram" cx="20%" cy="30%" r="50%">
      <stop offset="0%" stop-color="{accent}" stop-opacity="0.25" />
      <stop offset="100%" stop-color="{accent}" stop-opacity="0" />
    </radialGradient>
  </defs>

  <!-- Background Canvas -->
  <rect width="1536" height="1024" fill="url(#bgGramGrad)" />
  <rect width="1536" height="1024" fill="url(#glowGram)" />

  <!-- Decorative Top Banner -->
  <g transform="translate(98, 70)">
    <rect width="360" height="40" rx="20" fill="{accent}" fill-opacity="0.15" stroke="{accent}" stroke-width="1.5" />
    <circle cx="24" cy="20" r="6" fill="{accent}" />
    <text x="42" y="26" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif" font-size="15" font-weight="800" fill="#ffffff" letter-spacing="1">K-POP GRAMMAR BLUEPRINT 02</text>
  </g>

  <!-- Headline -->
  <g transform="translate(98, 160)">
    <text x="0" y="0" font-family="-apple-system, BlinkMacSystemFont, 'Pretendard', sans-serif" font-size="44" font-weight="900" fill="#ffffff" letter-spacing="-1">
      {escape(clean_text(song_title, 25))} - Essential Grammar Deep Dive
    </text>
    <text x="0" y="44" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif" font-size="22" font-weight="500" fill="#94a3b8">
      Sentence Formulas • Verb Conjugation • Everyday Conversational Application
    </text>
  </g>

  <!-- Central Cards -->
  {cards_svg}

  <!-- Footer Bar -->
  <g transform="translate(98, 880)">
    <rect width="1340" height="56" rx="16" fill="#090514" fill-opacity="0.95" stroke="#334155" stroke-width="1.5" />
    <circle cx="28" cy="28" r="6" fill="{accent}" />
    <text x="48" y="34" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif" font-size="18" font-weight="700" fill="#fde68a">
      TOPIK &amp; CEFR Standard Grammar Framework
    </text>
    <text x="500" y="34" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif" font-size="16" font-weight="500" fill="#94a3b8">
      | Structured Educational Architecture for Korean Fluency
    </text>
    <text x="1310" y="34" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif" font-size="16" font-weight="700" fill="{accent}" text-anchor="end">
      kpop-hangul.github.io
    </text>
  </g>
</svg>"""
    return svg.strip()


def convert_svg_to_webp(svg_path: Path, webp_path: Path) -> bool:
    """Converts SVG to 1536x1024 high-efficiency WebP using ffmpeg from PATH or environment."""
    webp_path.parent.mkdir(parents=True, exist_ok=True)
    import shutil
    ffmpeg_bin = os.getenv("FFMPEG_PATH") or shutil.which("ffmpeg") or "/usr/bin/ffmpeg"
    try:
        cmd = [
            ffmpeg_bin, "-y",
            "-i", str(svg_path),
            "-update", "1",
            "-frames:v", "1",
            "-vf", "scale=1536:1024",
            "-c:v", "libwebp",
            "-lossless", "0",
            "-q:v", "85",
            str(webp_path)
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        return res.returncode == 0 and webp_path.exists()
    except Exception as e:
        print(f"⚠️ [article_image_generator] ffmpeg conversion failed: {e}")
        return False


def build_figure_block(asset_key: str, relative_url: str, alt: str, caption: str) -> str:
    """Builds standard Astro figure markdown element."""
    return (
        f"<!-- article-illustration:{asset_key} -->\n"
        f'<figure class="article-illustration my-8 block">\n'
        f'  <img src="{escape(relative_url, quote=True)}" alt="{escape(alt, quote=True)}" '
        f'width="1536" height="1024" loading="lazy" decoding="async" '
        f'class="w-full h-auto rounded-2xl border border-slate-200 shadow-md object-cover" />\n'
        f'  <figcaption class="mt-2.5 text-center text-xs sm:text-sm text-slate-500 font-medium leading-relaxed">'
        f'{escape(caption, quote=True)}</figcaption>\n'
        f'</figure>\n'
        f'<!-- /article-illustration:{asset_key} -->'
    )


def generate_and_integrate_article_images(
    article: Dict[str, Any],
    slug: str,
    output_dir: Optional[Path] = None,
    site_prefix: str = SITE_PREFIX
) -> Tuple[str, List[Dict[str, Any]]]:
    """
    Generates 2 contextual learning diagrams (WebP) for the article and injects them
    at Section 2 (Chorus Breakdown) and Section 4 (Grammar Deep Dive).
    Returns (updated_markdown_content, generated_images_meta).
    """
    content = article.get("markdown_content", "")
    song_title = article.get("songTitle", article.get("song_title", article.get("title", "K-Pop Song")))
    artist = article.get("artist", "Various Artists")
    difficulty = article.get("difficulty", "Beginner")
    genre = article.get("genre", "Dance & Pop")

    out_dir = Path(output_dir) if output_dir else PUBLIC_IMG_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    # Check if already generated
    existing_figures = re.findall(r"<!-- article-illustration:([A-Za-z0-9_.-]+) -->", content)
    if len(existing_figures) >= 2:
        return content, [
            {"relative_url": f"/images/articles/{f}.webp", "asset_key": f} for f in existing_figures
        ]

    generated_images = []

    # 1. First Illustration: Chorus & Phonetic Rules
    key1 = f"{site_prefix}-{slug}-01"
    svg1_path = out_dir / f"{key1}.svg"
    webp1_path = out_dir / f"{key1}.webp"

    cards1 = [
        {
            "title": "Syllable Anatomy (음절)",
            "badge": "BLOCK STRUCTURE",
            "desc1": "Initial Consonant (초성) + Medial Vowel (중성)",
            "desc2": "Final Consonant (받침) adds sound depth",
            "desc3": "Visual 2-D block layout for every beat",
            "highlight": "Master the 3-Layer Block"
        },
        {
            "title": "Sound Linking (연음 법칙)",
            "badge": "LIAISON RULE",
            "desc1": "Final batchim slides over to next vowel",
            "desc2": "Eliminates pauses between lyric lines",
            "desc3": "Essential for singing with natural speed",
            "highlight": "Batchim -> Next Vowel Slide"
        },
        {
            "title": "Chorus Hook Active Recall",
            "badge": "VOCABULARY",
            "desc1": "Accurate Revised Romanization guide",
            "desc2": "Word-for-word literal particle gloss",
            "desc3": "Emotional nuance behind the artist lyric",
            "highlight": "Natural Spoken Flow"
        }
    ]

    svg1_code = generate_lyrics_phonetics_svg(song_title, artist, difficulty, genre, cards1)
    svg1_path.write_text(svg1_code, encoding="utf-8")

    converted1 = convert_svg_to_webp(svg1_path, webp1_path)
    url1 = f"/images/articles/{key1}.webp" if converted1 else f"/images/articles/{key1}.svg"

    fig1 = build_figure_block(
        key1,
        url1,
        f"{artist} - {song_title} Lyrics and Phonetic Sound Change Diagram",
        f"Figure 1: {artist} - '{song_title}' Syllable Block Structure, Phonetic Linking (연음), and Chorus Flow Guide"
    )

    generated_images.append({"relative_url": url1, "asset_key": key1, "kind": "lyrics_phonetics"})

    # 2. Second Illustration: Grammar Formulas & Conversational Patterns
    key2 = f"{site_prefix}-{slug}-02"
    svg2_path = out_dir / f"{key2}.svg"
    webp2_path = out_dir / f"{key2}.webp"

    cards2 = [
        {
            "title": "Grammar Formula 1",
            "badge": "CORE PATTERN",
            "desc1": "Direct attachment to verb / adjective stems",
            "desc2": "Vowel vs Consonant stem suffix rules",
            "desc3": "Key lyric anchor in the pre-chorus/hook",
            "highlight": "Verb Stem + Target Suffix"
        },
        {
            "title": "Grammar Formula 2",
            "badge": "CONNECTIVE",
            "desc1": "Expresses condition, time, or emotion",
            "desc2": "Creates smooth flow between musical phrases",
            "desc3": "High-frequency conversational pattern",
            "highlight": "Spoken Conversational Formula"
        },
        {
            "title": "Conversational Nuance",
            "badge": "SPOKEN TIPS",
            "desc1": "Informal casual (반말) in lyrics",
            "desc2": "Polite everyday standard (존댓말) match",
            "desc3": "Cultural context & natural tone tips",
            "highlight": "Formality & Tone Balance"
        }
    ]

    svg2_code = generate_grammar_patterns_svg(song_title, artist, difficulty, genre, cards2)
    svg2_path.write_text(svg2_code, encoding="utf-8")

    converted2 = convert_svg_to_webp(svg2_path, webp2_path)
    url2 = f"/images/articles/{key2}.webp" if converted2 else f"/images/articles/{key2}.svg"

    fig2 = build_figure_block(
        key2,
        url2,
        f"{artist} - {song_title} Korean Grammar Formula and Sentence Patterns",
        f"Figure 2: {artist} - '{song_title}' Key Grammar Formulas, Conjugation Patterns, and Conversational Usage"
    )

    generated_images.append({"relative_url": url2, "asset_key": key2, "kind": "grammar_patterns"})

    # Also sync to dist if dist exists
    if DIST_IMG_DIR.exists():
        DIST_IMG_DIR.mkdir(parents=True, exist_ok=True)
        for p in [svg1_path, webp1_path, svg2_path, webp2_path]:
            if p.exists():
                (DIST_IMG_DIR / p.name).write_bytes(p.read_bytes())

    # Insert Figure 1 before Section 3 (Vocabulary Table) or after Section 2 (Chorus Breakdown)
    if "## 3. Core Vocabulary Table" in content:
        content = content.replace("## 3. Core Vocabulary Table", f"{fig1}\n\n## 3. Core Vocabulary Table", 1)
    elif "## 2. Key Lyrics Breakdown" in content:
        # After section 2
        parts = content.split("## 2. Key Lyrics Breakdown")
        content = parts[0] + "## 2. Key Lyrics Breakdown" + parts[1] + f"\n\n{fig1}\n\n"

    # Insert Figure 2 before Section 5 (Pronunciation Secrets) or after Section 4 (Grammar Deep Dive)
    if "## 5. Pronunciation Secrets" in content:
        content = content.replace("## 5. Pronunciation Secrets", f"{fig2}\n\n## 5. Pronunciation Secrets", 1)
    elif "## 4. Essential Grammar Deep Dive" in content:
        # If no Section 5, before Section 6
        if "## 6. Cultural Context" in content:
            content = content.replace("## 6. Cultural Context", f"{fig2}\n\n## 6. Cultural Context", 1)
        else:
            content += f"\n\n{fig2}\n\n"

    return content, generated_images
