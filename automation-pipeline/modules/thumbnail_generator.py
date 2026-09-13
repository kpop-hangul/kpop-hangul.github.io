"""
K-Pop Hangul Blog SVG Thumbnail Generator
Generates high-resolution 1200x630 SVGs for every song lesson.
Features K-Pop neon cyber/retro aesthetics, audio waveform visualizers, vinyl grooves,
Hangul typography, and clear difficulty & chart badges.
"""
import os
import re
from html import escape
from pathlib import Path
from typing import Dict, Any, Optional, List

BASE_DIR = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = BASE_DIR / "blog-frontend" / "public" / "images" / "thumbnails"
DEFAULT_DIST_DIR = BASE_DIR / "blog-frontend" / "dist" / "images" / "thumbnails"

DIFFICULTY_THEMES = {
    "beginner": {
        "bg_stops": [("#032b26", "0%"), ("#064e3b", "45%"), ("#021c18", "100%")],
        "accent": "#2dd4bf",
        "glow": "#14b8a6",
        "pill_bg": "#134e4a",
        "pill_border": "#2dd4bf",
        "pill_text": "#ccfbf1",
        "badge": "🟢 Beginner (Level 1)",
        "watermark": "한글 기초",
        "tagline": "Easy Syllables & Catchy Hooks"
    },
    "intermediate": {
        "bg_stops": [("#0f0c29", "0%"), ("#1e1b4b", "50%"), ("#080614", "100%")],
        "accent": "#a855f7",
        "glow": "#818cf8",
        "pill_bg": "#312e81",
        "pill_border": "#818cf8",
        "pill_text": "#e0e7ff",
        "badge": "🟡 Intermediate (Level 2)",
        "watermark": "가사 문법",
        "tagline": "Conversational Patterns & Nuances"
    },
    "advanced": {
        "bg_stops": [("#200319", "0%"), ("#4a044e", "50%"), ("#0f020c", "100%")],
        "accent": "#f43f5e",
        "glow": "#fb7185",
        "pill_bg": "#701a75",
        "pill_border": "#f43f5e",
        "pill_text": "#fdf2f8",
        "badge": "🔴 Advanced (Level 3)",
        "watermark": "심화 어휘",
        "tagline": "Fast Flow & Poetic Idioms"
    }
}


def clean_text(s: str, max_len: int = 50) -> str:
    s = re.sub(r"[#*`_~]", "", str(s)).strip()
    return s[:max_len] + ("..." if len(s) > max_len else "")


def split_title(title: str, max_len: int = 24) -> List[str]:
    words = title.split()
    lines = []
    curr = ""
    for w in words:
        if len(curr + " " + w) > max_len and curr:
            lines.append(curr.strip())
            curr = w
        else:
            curr = (curr + " " + w).strip()
    if curr:
        lines.append(curr.strip())
    if len(lines) > 2:
        lines = lines[:2]
        lines[1] += "..."
    return lines


def generate_kpop_svg_thumbnail(post_data: Dict[str, Any]) -> str:
    """Creates a 1200x630 vector SVG thumbnail for a K-Pop lesson."""
    title = post_data.get("title", "")
    artist = post_data.get("artist", "K-Pop Artist")
    song_title = post_data.get("songTitle", post_data.get("song_title", ""))
    hangul_title = post_data.get("hangulTitle", post_data.get("hangul_title", ""))
    difficulty = str(post_data.get("difficulty", "Beginner")).lower()
    genre = post_data.get("genre", "Dance & Pop")
    chart_rank = post_data.get("chartRank", post_data.get("chart_rank", None))
    chart_source = post_data.get("chartSource", "Melon Top 100")

    diff_key = "beginner"
    if "inter" in difficulty or "2" in difficulty:
        diff_key = "intermediate"
    elif "adv" in difficulty or "3" in difficulty:
        diff_key = "advanced"

    theme = DIFFICULTY_THEMES[diff_key]

    # Chart badge text
    if chart_rank:
        rank_badge = f"🏆 {chart_source} #{chart_rank}"
    else:
        rank_badge = f"🔥 Top Chart Pick"

    # Display song name prominently
    display_song = song_title or title
    if hangul_title:
        display_song_sub = f"{hangul_title} ({genre})"
    else:
        display_song_sub = f"{genre}"

    title_lines = split_title(display_song, max_len=20)
    line1 = escape(title_lines[0] if len(title_lines) > 0 else "K-Pop Hit")
    line2 = escape(title_lines[1] if len(title_lines) > 1 else "")

    if line2:
        line2_svg = f'<text x="0" y="62" font-family="-apple-system, BlinkMacSystemFont, Pretendard, Segoe UI, Roboto, sans-serif" font-size="46" font-weight="900" fill="#f1f5f9" letter-spacing="-1">{line2}</text>'
        sub_y = 230
        pills_y = 305
    else:
        line2_svg = ''
        sub_y = 175
        pills_y = 250

    artist_clean = escape(clean_text(artist, 28))
    rank_badge_esc = escape(rank_badge)
    badge_esc = escape(theme["badge"])
    tagline_esc = escape(theme["tagline"])
    watermark_esc = escape(theme["watermark"])
    song_sub_esc = escape(clean_text(display_song_sub, 35))

    # Soundwave bars generator
    bars_svg = ""
    bar_heights = [24, 45, 78, 120, 65, 95, 140, 110, 80, 135, 160, 90, 115, 150, 75, 50, 100, 85, 130, 60]
    start_bx = 960
    for i, h in enumerate(bar_heights):
        bx = start_bx + (i * 10)
        by = 315 - (h // 2)
        bars_svg += f'<rect x="{bx}" y="{by}" width="4" height="{h}" rx="2" fill="{theme["accent"]}" opacity="0.85" />\n'

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 630" width="1200" height="630">
  <defs>
    <!-- Background Gradient -->
    <linearGradient id="bgGrad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="{theme['bg_stops'][0][1]}" stop-color="{theme['bg_stops'][0][0]}" />
      <stop offset="{theme['bg_stops'][1][1]}" stop-color="{theme['bg_stops'][1][0]}" />
      <stop offset="{theme['bg_stops'][2][1]}" stop-color="{theme['bg_stops'][2][0]}" />
    </linearGradient>

    <!-- Accent Glow Gradient -->
    <radialGradient id="glowGrad" cx="80%" cy="30%" r="60%">
      <stop offset="0%" stop-color="{theme['glow']}" stop-opacity="0.32" />
      <stop offset="60%" stop-color="{theme['glow']}" stop-opacity="0.06" />
      <stop offset="100%" stop-color="{theme['glow']}" stop-opacity="0" />
    </radialGradient>

    <!-- Vinyl Center Radial -->
    <radialGradient id="vinylCenter" cx="50%" cy="50%" r="50%">
      <stop offset="0%" stop-color="{theme['accent']}" />
      <stop offset="50%" stop-color="{theme['pill_bg']}" />
      <stop offset="100%" stop-color="#09090b" />
    </radialGradient>
  </defs>

  <!-- Canvas Background -->
  <rect width="1200" height="630" fill="url(#bgGrad)" />
  <rect width="1200" height="630" fill="url(#glowGrad)" />

  <!-- Grid Tech Lines -->
  <g opacity="0.08" stroke="#ffffff" stroke-width="1">
    <line x1="0" y1="90" x2="1200" y2="90" />
    <line x1="0" y1="180" x2="1200" y2="180" />
    <line x1="0" y1="270" x2="1200" y2="270" />
    <line x1="0" y1="360" x2="1200" y2="360" />
    <line x1="0" y1="450" x2="1200" y2="450" />
    <line x1="0" y1="540" x2="1200" y2="540" />
    <line x1="200" y1="0" x2="200" y2="630" />
    <line x1="400" y1="0" x2="400" y2="630" />
    <line x1="600" y1="0" x2="600" y2="630" />
    <line x1="800" y1="0" x2="800" y2="630" />
    <line x1="1000" y1="0" x2="1000" y2="630" />
  </g>

  <!-- Giant Background Hangul Watermark -->
  <text x="1140" y="440" font-family="-apple-system, BlinkMacSystemFont, 'Pretendard', sans-serif"
        font-size="140" font-weight="900" fill="#ffffff" opacity="0.04" text-anchor="end">{watermark_esc}</text>

  <!-- Right Visual: Stylized Neon Vinyl & Equalizer -->
  <g transform="translate(980, 315)">
    <!-- Vinyl Grooves -->
    <circle cx="0" cy="0" r="210" fill="#09090b" stroke="{theme['accent']}" stroke-width="3" opacity="0.9" />
    <circle cx="0" cy="0" r="185" fill="none" stroke="#27272a" stroke-width="1.5" />
    <circle cx="0" cy="0" r="160" fill="none" stroke="#27272a" stroke-width="1.5" />
    <circle cx="0" cy="0" r="135" fill="none" stroke="#3f3f46" stroke-width="1.5" />
    <circle cx="0" cy="0" r="110" fill="none" stroke="#27272a" stroke-width="1.5" />
    <circle cx="0" cy="0" r="85" fill="none" stroke="{theme['accent']}" stroke-width="1" opacity="0.6" />

    <!-- Vinyl Center Label -->
    <circle cx="0" cy="0" r="62" fill="url(#vinylCenter)" stroke="{theme['accent']}" stroke-width="2.5" />
    <circle cx="0" cy="0" r="14" fill="#ffffff" />

    <!-- Floating Musical Notes -->
    <text x="-160" y="-140" font-family="'Segoe UI', sans-serif" font-size="34" fill="{theme['accent']}" opacity="0.75">♫</text>
    <text x="140" y="-120" font-family="'Segoe UI', sans-serif" font-size="28" fill="{theme['glow']}" opacity="0.8">♬</text>
    <text x="-140" y="150" font-family="'Segoe UI', sans-serif" font-size="30" fill="{theme['accent']}" opacity="0.7">♪</text>
  </g>

  <!-- Equalizer Visualizer Spectrum -->
  <g>
    {bars_svg}
  </g>

  <!-- Left Content Area -->
  <g transform="translate(80, 80)">
    <!-- Badges Row -->
    <g>
      <!-- Difficulty Pill -->
      <rect x="0" y="0" width="210" height="38" rx="19" fill="{theme['pill_bg']}" stroke="{theme['pill_border']}" stroke-width="1.5" />
      <text x="105" y="24" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif"
            font-size="14" font-weight="700" fill="{theme['pill_text']}" text-anchor="middle">{badge_esc}</text>

      <!-- Chart Source & Rank Pill -->
      <rect x="222" y="0" width="220" height="38" rx="19" fill="#18181b" stroke="#3f3f46" stroke-width="1.5" />
      <text x="332" y="24" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif"
            font-size="13" font-weight="700" fill="#fde047" text-anchor="middle">{rank_badge_esc}</text>
    </g>

    <!-- Artist Subheading -->
    <g transform="translate(0, 82)">
      <text x="0" y="0" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif"
            font-size="24" font-weight="800" fill="{theme['accent']}" letter-spacing="3" text-transform="uppercase">
        {artist_clean}
      </text>
    </g>

    <!-- Main Song Title -->
    <g transform="translate(0, 150)">
      <text x="0" y="0" font-family="-apple-system, BlinkMacSystemFont, 'Pretendard', 'Segoe UI', Roboto, sans-serif"
            font-size="52" font-weight="900" fill="#ffffff" letter-spacing="-1">
        {line1}
      </text>
      {line2_svg}
    </g>

    <!-- Subtitle / Hangul and Genre info -->
    <g transform="translate(0, {sub_y})">
      <text x="0" y="15" font-family="-apple-system, BlinkMacSystemFont, 'Pretendard', sans-serif"
            font-size="20" font-weight="600" fill="#94a3b8">
        {song_sub_esc} • {tagline_esc}
      </text>
    </g>

    <!-- 3 Core Pedagogy Pillars -->
    <g transform="translate(0, {pills_y})">
      <rect x="0" y="0" width="580" height="52" rx="14" fill="#0f172a" fill-opacity="0.85" stroke="#334155" stroke-width="1.5" />
      <text x="24" y="32" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif"
            font-size="14" font-weight="700" fill="#e2e8f0">
        📝 3-Line Breakdown  •  📚 Core Vocab Table  •  🗣️ Pronunciation Guide
      </text>
    </g>
  </g>

  <!-- Bottom Branding Bar -->
  <g transform="translate(80, 560)">
    <rect width="1040" height="42" rx="10" fill="#09090b" fill-opacity="0.75" stroke="#27272a" stroke-width="1" />
    <circle cx="24" cy="21" r="5" fill="{theme['accent']}" />
    <text x="38" y="26" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif"
          font-size="13" font-weight="700" fill="#e4e4e7">
      K-Pop Hangul • Master Korean Lyrics with Melon &amp; Spotify Hits
    </text>
    <text x="1016" y="26" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif"
          font-size="13" font-weight="700" fill="{theme['accent']}" text-anchor="end">
      kpop-hangul.github.io
    </text>
  </g>
</svg>"""
    return svg.strip()


def generate_thumbnail_for_post(
    post_data: Dict[str, Any],
    output_dir: Optional[Path] = None
) -> str:
    """Generates and writes an SVG thumbnail for a post, returning its public URL."""
    slug = post_data.get("slug", "kpop-song")
    target_dir = Path(output_dir) if output_dir else DEFAULT_OUTPUT_DIR
    target_dir.mkdir(parents=True, exist_ok=True)

    svg_content = generate_kpop_svg_thumbnail(post_data)
    target_file = target_dir / f"{slug}.svg"
    target_file.write_text(svg_content, encoding="utf-8")

    # Also copy to dist if dist exists
    if DEFAULT_DIST_DIR.exists():
        DEFAULT_DIST_DIR.mkdir(parents=True, exist_ok=True)
        (DEFAULT_DIST_DIR / f"{slug}.svg").write_text(svg_content, encoding="utf-8")

    return f"/images/thumbnails/{slug}.svg"
