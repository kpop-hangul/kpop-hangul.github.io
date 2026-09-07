/**
 * URL Slug and Category Helper Functions for 100% 404-Free GitHub Pages Navigation
 */

export function getCategorySlug(category: string = ''): string {
  const normalized = category.trim().toLowerCase();
  
  // 1. 대표 카테고리 매핑
  if (normalized.includes('ai') || normalized.includes('생산성') || normalized.includes('productivity')) {
    return 'ai-productivity';
  }
  if (normalized.includes('개발') || normalized.includes('테크') || normalized.includes('dev') || normalized.includes('tech')) {
    return 'tech-dev';
  }
  if (normalized.includes('부업') || normalized.includes('재테크') || normalized.includes('income')) {
    return 'side-income';
  }
  if (normalized.includes('마케팅') || normalized.includes('marketing')) {
    return 'marketing';
  }
  if (normalized.includes('클라우드') || normalized.includes('인프라') || normalized.includes('cloud')) {
    return 'cloud-infra';
  }

  // 2. 신규/기타 카테고리 (한글 및 영문 지원)
  const slugified = normalized
    .replace(/&/g, 'and')
    .replace(/[\s\/\\]+/g, '-')
    .replace(/[^\w\uAC00-\uD7A3-]/g, '')
    .replace(/--+/g, '-')
    .replace(/^-+|-+$/g, '');

  return slugified || 'general';
}

export function getCategoryName(slug: string, fallbackName: string = ''): string {
  const map: Record<string, string> = {
    'ai-productivity': 'AI & 생산성',
    'tech-dev': '개발 & 테크',
    'side-income': '스마트 부업',
    'marketing': '마케팅 & 브랜딩',
    'cloud-infra': '클라우드 & 인프라',
    'general': '일반 테크',
  };
  if (map[slug]) return map[slug];
  if (fallbackName && fallbackName.trim()) return fallbackName.trim();
  return slug.replace(/-/g, ' ').toUpperCase();
}

export function getTagSlug(tag: string = ''): string {
  return tag
    .trim()
    .toLowerCase()
    .replace(/&/g, 'and')
    .replace(/[\s\/\\]+/g, '-')
    .replace(/[^\w\uAC00-\uD7A3-]/g, '')
    .replace(/--+/g, '-')
    .replace(/^-+|-+$/g, '') || 'tag';
}
