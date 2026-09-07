import { getCollection } from 'astro:content';
import { getCategorySlug, getTagSlug } from '../utils/slug';

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
      category: post.data.category || 'General',
      categorySlug: getCategorySlug(post.data.category || 'General'),
      tags: post.data.tags || [],
      pubDate: new Intl.DateTimeFormat('ko-KR', {
        year: 'numeric',
        month: 'long',
        day: 'numeric',
      }).format(post.data.pubDate),
      readingTime: post.data.readingTime || '5 min read',
    }));

  return new Response(JSON.stringify(searchData), {
    headers: {
      'Content-Type': 'application/json',
      'Cache-Control': 'public, max-age=3600',
    },
  });
}
