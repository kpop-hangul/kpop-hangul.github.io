import { getCollection } from 'astro:content';
import siteConfig from '../../config/site';

export async function getStaticPaths() {
  const posts = await getCollection('blog', ({ data }) => !data.draft);
  return posts.map((post) => ({
    params: { slug: post.slug },
    props: { post },
  }));
}

export async function GET({ props }: any) {
  const { post } = props;
  const title = post.data.title || 'K-Pop Korean Lesson';
  const category = post.data.difficulty || post.data.category || 'Beginner (Level 1)';
  const genre = post.data.genre || 'Dance & Pop';
  const readingTime = post.data.readingTime || '6 min read';
  const pubDate = new Intl.DateTimeFormat('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  }).format(post.data.pubDate);

  // Split title across up to 3 lines
  const words = title.split(' ');
  const lines: string[] = [];
  let currentLine = '';

  for (const word of words) {
    if ((currentLine + ' ' + word).trim().length > 24) {
      if (currentLine) lines.push(currentLine.trim());
      currentLine = word;
    } else {
      currentLine = (currentLine + ' ' + word).trim();
    }
  }
  if (currentLine) lines.push(currentLine.trim());
  const displayLines = lines.slice(0, 3);

  // Escape XML entities
  const escapeXml = (unsafe: string) =>
    unsafe
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&apos;');

  const titleSvgText = displayLines
    .map((line, idx) => `<tspan x="80" dy="${idx === 0 ? 0 : 54}">${escapeXml(line)}</tspan>`)
    .join('');

  const svg = `
<svg width="1200" height="630" viewBox="0 0 1200 630" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <linearGradient id="bgGrad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#090d16" />
      <stop offset="50%" stop-color="#1e1b4b" />
      <stop offset="100%" stop-color="#0f172a" />
    </linearGradient>
    <linearGradient id="brandGrad" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%" stop-color="#6366f1" />
      <stop offset="50%" stop-color="#a855f7" />
      <stop offset="100%" stop-color="#ec4899" />
    </linearGradient>
    <linearGradient id="cardGrad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#ffffff" stop-opacity="0.09" />
      <stop offset="100%" stop-color="#ffffff" stop-opacity="0.02" />
    </linearGradient>
  </defs>

  <!-- Background -->
  <rect width="1200" height="630" fill="url(#bgGrad)" />

  <!-- Ambient Glows -->
  <circle cx="1050" cy="150" r="350" fill="#a855f7" opacity="0.22" filter="blur(90px)" />
  <circle cx="150" cy="500" r="300" fill="#ec4899" opacity="0.16" filter="blur(80px)" />
  <circle cx="600" cy="300" r="250" fill="#4f46e5" opacity="0.14" filter="blur(80px)" />

  <!-- Inner Card -->
  <rect x="50" y="50" width="1100" height="530" rx="32" fill="url(#cardGrad)" stroke="#ffffff" stroke-opacity="0.15" stroke-width="1.5" />

  <!-- Brand Header -->
  <g transform="translate(80, 95)">
    <rect x="0" y="0" width="42" height="42" rx="12" fill="url(#brandGrad)" />
    <text x="14" y="28" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif" font-size="20" font-weight="black" fill="#ffffff">🎵</text>
    <text x="56" y="28" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif" font-size="22" font-weight="900" fill="#ffffff" letter-spacing="-0.5">${siteConfig.site.shortName || 'K-Pop Hangul'}</text>
    <text x="210" y="28" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif" font-size="16" fill="#c084fc">Learn Korean with K-Pop Hits</text>
  </g>

  <!-- Badges -->
  <g transform="translate(80, 175)">
    <rect x="0" y="0" width="${escapeXml(category).length * 13 + 30}" height="32" rx="16" fill="#312e81" stroke="#6366f1" stroke-width="1.2" />
    <text x="15" y="21" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif" font-size="13" font-weight="700" fill="#c7d2fe">${escapeXml(category)}</text>
    
    <text x="${escapeXml(category).length * 13 + 45}" y="21" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif" font-size="13" font-weight="600" fill="#f472b6">• ${escapeXml(genre)}</text>
    <text x="${escapeXml(category).length * 13 + escapeXml(genre).length * 9 + 75}" y="21" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif" font-size="13" fill="#94a3b8">• ${escapeXml(readingTime)}</text>
  </g>

  <!-- Post Title -->
  <text x="80" y="290" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Pretendard', sans-serif" font-size="42" font-weight="800" fill="#ffffff" letter-spacing="-1" line-height="1.3">
    ${titleSvgText}
  </text>

  <!-- Footer Info -->
  <g transform="translate(80, 520)">
    <text x="0" y="0" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif" font-size="15" fill="#94a3b8">Published: ${pubDate} | kpop-hangul.github.io</text>
    <text x="940" y="0" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif" font-size="16" font-weight="bold" fill="#ec4899" text-anchor="end">Start Korean Lesson →</text>
  </g>
</svg>
`.trim();

  return new Response(svg, {
    headers: {
      'Content-Type': 'image/svg+xml; charset=utf-8',
      'Cache-Control': 'public, max-age=31536000, immutable',
    },
  });
}
