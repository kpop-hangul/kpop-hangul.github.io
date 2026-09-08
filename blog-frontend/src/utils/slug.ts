/**
 * URL Slug and Category Helper Functions for K-Pop Korean Learning Blog
 */

// 1. Difficulty Level Slugs & Names
export function getDifficultySlug(difficulty: string = ''): string {
  const norm = difficulty.trim().toLowerCase();
  if (norm.includes('begin') || norm.includes('level 1') || norm.includes('초급')) return 'beginner';
  if (norm.includes('inter') || norm.includes('level 2') || norm.includes('중급')) return 'intermediate';
  if (norm.includes('adv') || norm.includes('level 3') || norm.includes('고급')) return 'advanced';
  return 'beginner';
}

export function getDifficultyName(slugOrName: string = ''): string {
  const slug = getDifficultySlug(slugOrName);
  const map: Record<string, { name: string; level: string; badge: string; desc: string }> = {
    beginner: {
      name: 'Beginner (Level 1)',
      level: 'Level 1',
      badge: '🟢 Beginner',
      desc: 'Basic Hangul, repetitive catchy chorus lines, everyday vocabulary & simple grammar patterns.',
    },
    intermediate: {
      name: 'Intermediate (Level 2)',
      level: 'Level 2',
      badge: '🟡 Intermediate',
      desc: 'Conversational phrases, idiomatic expressions, verb conjugations & emotional lyrics.',
    },
    advanced: {
      name: 'Advanced (Level 3)',
      level: 'Level 3',
      badge: '🔴 Advanced',
      desc: 'Fast rap bars, complex metaphorical expressions, wordplay & nuanced poetic Korean.',
    },
  };
  return map[slug]?.name || 'Beginner (Level 1)';
}

// 2. Genre Slugs & Names
export function getGenreSlug(genre: string = ''): string {
  const norm = genre.trim().toLowerCase();
  if (norm.includes('dance') || norm.includes('pop')) return 'dance-pop';
  if (norm.includes('r&b') || norm.includes('rnb') || norm.includes('soul')) return 'rnb-soul';
  if (norm.includes('hip') || norm.includes('rap')) return 'hip-hop';
  if (norm.includes('ballad') || norm.includes('ost')) return 'ballad-ost';
  if (norm.includes('rock') || norm.includes('band')) return 'rock-band';
  if (norm.includes('indie') || norm.includes('acoustic')) return 'indie-acoustic';

  return norm
    .replace(/&/g, 'and')
    .replace(/[\s\/\\]+/g, '-')
    .replace(/[^\w-]/g, '')
    .replace(/--+/g, '-')
    .replace(/^-+|-+$/g, '') || 'dance-pop';
}

export function getGenreName(slug: string, fallback: string = ''): string {
  const map: Record<string, string> = {
    'dance-pop': 'Dance & Pop',
    'rnb-soul': 'R&B & Soul',
    'hip-hop': 'Hip-Hop & Rap',
    'ballad-ost': 'Ballad & OST',
    'rock-band': 'Rock & Band',
    'indie-acoustic': 'Indie & Acoustic',
  };
  if (map[slug]) return map[slug];
  if (fallback && fallback.trim()) return fallback.trim();
  return slug.split('-').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ');
}

// 3. Artist Slugs & Names
export function getArtistSlug(artist: string = ''): string {
  return artist
    .trim()
    .toLowerCase()
    .replace(/\s*\([^)]*\)/g, '') // remove brackets like (빅뱅)
    .replace(/&/g, 'and')
    .replace(/[\s\/\\]+/g, '-')
    .replace(/[^\w\uAC00-\uD7A3-]/g, '')
    .replace(/--+/g, '-')
    .replace(/^-+|-+$/g, '') || 'various-artists';
}

// 4. General Category Slugs & Names
export function getCategorySlug(category: string = ''): string {
  const norm = category.trim().toLowerCase();
  if (norm.includes('begin') || norm.includes('level 1')) return 'beginner';
  if (norm.includes('inter') || norm.includes('level 2')) return 'intermediate';
  if (norm.includes('adv') || norm.includes('level 3')) return 'advanced';
  if (norm.includes('dance') || norm.includes('pop')) return 'dance-pop';
  if (norm.includes('r&b') || norm.includes('rnb') || norm.includes('soul')) return 'rnb-soul';
  if (norm.includes('hip') || norm.includes('rap')) return 'hip-hop';
  if (norm.includes('ballad') || norm.includes('ost')) return 'ballad-ost';
  if (norm.includes('rock') || norm.includes('band')) return 'rock-band';

  return norm
    .replace(/&/g, 'and')
    .replace(/[\s\/\\]+/g, '-')
    .replace(/[^\w\uAC00-\uD7A3-]/g, '')
    .replace(/--+/g, '-')
    .replace(/^-+|-+$/g, '') || 'general';
}

export function getCategoryName(slug: string, fallbackName: string = ''): string {
  const map: Record<string, string> = {
    'beginner': 'Beginner (Level 1)',
    'intermediate': 'Intermediate (Level 2)',
    'advanced': 'Advanced (Level 3)',
    'dance-pop': 'Dance & Pop',
    'rnb-soul': 'R&B & Soul',
    'hip-hop': 'Hip-Hop & Rap',
    'ballad-ost': 'Ballad & OST',
    'rock-band': 'Rock & Band',
    'indie-acoustic': 'Indie & Acoustic',
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
    .replace(/^-+|-+$/g, '') || 'kpop';
}

