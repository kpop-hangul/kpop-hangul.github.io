import { getCollection } from 'astro:content';
import { getCategorySlug, getDifficultySlug, getGenreSlug, getArtistSlug } from '../utils/slug';

export async function GET() {
  const posts = await getCollection('blog', ({ data }) => {
    return import.meta.env.PROD ? !data.draft : true;
  });

  const searchData = posts
    .sort((a, b) => b.data.pubDate.valueOf() - a.data.pubDate.valueOf())
    .map(post => ({
      title: post.data.title,
      description: post.data.description,
      slug: post.slug,
      category: post.data.category || 'Beginner (Level 1)',
      categorySlug: getCategorySlug(post.data.category || ''),
      difficulty: post.data.difficulty || 'Beginner',
      difficultySlug: getDifficultySlug(post.data.difficulty || ''),
      genre: post.data.genre || 'Dance & Pop',
      genreSlug: getGenreSlug(post.data.genre || ''),
      artist: post.data.artist || 'Various Artists',
      artistSlug: getArtistSlug(post.data.artist || ''),
      songTitle: post.data.songTitle || '',
      hangulTitle: post.data.hangulTitle || '',
      chartRank: post.data.chartRank,
      chartSource: post.data.chartSource || 'Melon Top 100',
      tags: post.data.tags || [],
      pubDate: new Intl.DateTimeFormat('en-US', {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
      }).format(post.data.pubDate),
      readingTime: post.data.readingTime || '6 min read',
    }));

  return new Response(JSON.stringify(searchData), {
    headers: {
      'Content-Type': 'application/json',
      'Cache-Control': 'public, max-age=3600',
    },
  });
}

