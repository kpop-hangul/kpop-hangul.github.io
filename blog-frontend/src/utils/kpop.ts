import { getCollection } from 'astro:content';
import { getDifficultySlug, getDifficultyName, getGenreSlug, getGenreName, getArtistSlug } from './slug';

export interface DifficultyInfo {
  slug: string;
  name: string;
  badge: string;
  count: number;
  description: string;
  href: string;
}

export interface GenreInfo {
  slug: string;
  name: string;
  count: number;
  href: string;
}

export interface ArtistInfo {
  name: string;
  slug: string;
  count: number;
  href: string;
  latestSong?: string;
}

export async function getDifficultyStats(): Promise<DifficultyInfo[]> {
  const base = import.meta.env.BASE_URL.replace(/\/$/, '');
  const posts = await getCollection('blog', ({ data }) => import.meta.env.PROD ? !data.draft : true);

  const levels: Record<string, { name: string; badge: string; desc: string }> = {
    beginner: {
      name: 'Beginner (Level 1)',
      badge: '🟢 Beginner',
      desc: 'Simple Hangul, repetitive catchy hook lines, essential everyday vocabulary and basic verb conjugations.'
    },
    intermediate: {
      name: 'Intermediate (Level 2)',
      badge: '🟡 Intermediate',
      desc: 'Conversational phrases, connectives, emotional nuances, and natural everyday spoken Korean.'
    },
    advanced: {
      name: 'Advanced (Level 3)',
      badge: '🔴 Advanced',
      desc: 'Fast rap verses, poetic metaphors, complex grammar patterns, and cultural wordplay.'
    }
  };

  const counts: Record<string, number> = { beginner: 0, intermediate: 0, advanced: 0 };
  for (const p of posts) {
    const d = getDifficultySlug(p.data.difficulty || p.data.category);
    counts[d] = (counts[d] || 0) + 1;
  }

  return (['beginner', 'intermediate', 'advanced'] as const).map(lvl => ({
    slug: lvl,
    name: levels[lvl].name,
    badge: levels[lvl].badge,
    count: counts[lvl] || 0,
    description: levels[lvl].desc,
    href: base + '/difficulty/' + lvl + '/'
  }));
}

export async function getGenreStats(): Promise<GenreInfo[]> {
  const base = import.meta.env.BASE_URL.replace(/\/$/, '');
  const posts = await getCollection('blog', ({ data }) => import.meta.env.PROD ? !data.draft : true);

  const counts: Record<string, { rawName: string; count: number }> = {};
  for (const p of posts) {
    const raw = p.data.genre || 'Dance & Pop';
    const slug = getGenreSlug(raw);
    if (!counts[slug]) counts[slug] = { rawName: raw, count: 0 };
    counts[slug].count++;
  }

  return Object.keys(counts)
    .sort((a, b) => counts[b].count - counts[a].count)
    .map(slug => ({
      slug,
      name: getGenreName(slug, counts[slug].rawName),
      count: counts[slug].count,
      href: base + '/genres/' + slug + '/'
    }));
}

export async function getArtistStats(): Promise<ArtistInfo[]> {
  const base = import.meta.env.BASE_URL.replace(/\/$/, '');
  const posts = await getCollection('blog', ({ data }) => import.meta.env.PROD ? !data.draft : true);

  const artistMap: Record<string, { name: string; count: number; latestSong: string; latestDate: number }> = {};
  for (const p of posts) {
    const artist = (p.data.artist || 'Various Artists').trim();
    const slug = getArtistSlug(artist);
    const pubTime = p.data.pubDate.valueOf();

    if (!artistMap[slug]) {
      artistMap[slug] = { name: artist, count: 0, latestSong: p.data.songTitle, latestDate: pubTime };
    }
    artistMap[slug].count++;
    if (pubTime > artistMap[slug].latestDate) {
      artistMap[slug].latestDate = pubTime;
      artistMap[slug].latestSong = p.data.songTitle;
    }
  }

  return Object.keys(artistMap)
    .sort((a, b) => artistMap[b].count - artistMap[a].count)
    .map(slug => ({
      name: artistMap[slug].name,
      slug,
      count: artistMap[slug].count,
      latestSong: artistMap[slug].latestSong,
      href: base + '/artists/' + slug + '/'
    }));
}
