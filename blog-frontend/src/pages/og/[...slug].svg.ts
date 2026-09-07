import { getCollection } from 'astro:content';

export async function getStaticPaths() {
  const posts = await getCollection('blog', ({ data }) => !data.draft);
  return posts.map((post) => ({
    params: { slug: post.slug },
    props: { post },
  }));
}

export async function GET({ props }: any) {
  const { post } = props;
  const title = post.data.title || '앱시안 블로그 포스팅';
  const category = post.data.category || 'AI & 생산성';
  const readingTime = post.data.readingTime || '5 min read';
  const pubDate = new Intl.DateTimeFormat('ko-KR', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  }).format(post.data.pubDate);

  // 긴 제목 분할 (25자 단위 최대 3줄)
  const words = title.split(' ');
  const lines: string[] = [];
  let currentLine = '';

  for (const word of words) {
    if ((currentLine + ' ' + word).trim().length > 22) {
      if (currentLine) lines.push(currentLine.trim());
      currentLine = word;
    } else {
      currentLine = (currentLine + ' ' + word).trim();
    }
  }
  if (currentLine) lines.push(currentLine.trim());
  const displayLines = lines.slice(0, 3);

  // XML 특수문자 이스케이프
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
      <stop offset="0%" stop-color="#0f172a" />
      <stop offset="50%" stop-color="#1e293b" />
      <stop offset="100%" stop-color="#090d16" />
    </linearGradient>
    <linearGradient id="blueGrad" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%" stop-color="#2563eb" />
      <stop offset="100%" stop-color="#38bdf8" />
    </linearGradient>
    <linearGradient id="cardGrad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#ffffff" stop-opacity="0.08" />
      <stop offset="100%" stop-color="#ffffff" stop-opacity="0.02" />
    </linearGradient>
  </defs>

  <!-- Background -->
  <rect width="1200" height="630" fill="url(#bgGrad)" />

  <!-- Ambient Glow -->
  <circle cx="1050" cy="150" r="350" fill="#2563eb" opacity="0.18" filter="blur(80px)" />
  <circle cx="150" cy="500" r="300" fill="#0ea5e9" opacity="0.12" filter="blur(70px)" />

  <!-- Inner Glass Card -->
  <rect x="50" y="50" width="1100" height="530" rx="32" fill="url(#cardGrad)" stroke="#ffffff" stroke-opacity="0.12" stroke-width="1.5" />

  <!-- Brand Header -->
  <g transform="translate(80, 100)">
    <rect x="0" y="0" width="38" height="38" rx="10" fill="#2563eb" />
    <text x="50" y="26" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif" font-size="20" font-weight="bold" fill="#ffffff" letter-spacing="-0.5">앱시안(absian)</text>
    <text x="175" y="26" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif" font-size="16" fill="#94a3b8">AI &amp; Tech Insights</text>
  </g>

  <!-- Category & Read Time Badge -->
  <g transform="translate(80, 180)">
    <rect x="0" y="0" width="${escapeXml(category).length * 18 + 36}" height="36" rx="18" fill="#1e3a8a" stroke="#3b82f6" stroke-width="1" />
    <text x="18" y="23" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif" font-size="15" font-weight="600" fill="#93c5fd">${escapeXml(category)}</text>
    <text x="${escapeXml(category).length * 18 + 50}" y="23" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif" font-size="15" fill="#64748b">• ${escapeXml(readingTime)}</text>
  </g>

  <!-- Post Title -->
  <text x="80" y="300" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Pretendard', sans-serif" font-size="44" font-weight="800" fill="#ffffff" letter-spacing="-1" line-height="1.3">
    ${titleSvgText}
  </text>

  <!-- Footer Info -->
  <g transform="translate(80, 520)">
    <text x="0" y="0" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif" font-size="16" fill="#64748b">발행일: ${pubDate} | absianp.github.io</text>
    <text x="940" y="0" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif" font-size="16" font-weight="bold" fill="#38bdf8" text-anchor="end">읽으러 가기 →</text>
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
