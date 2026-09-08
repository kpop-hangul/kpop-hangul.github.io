import rss from '@astrojs/rss';
import { getCollection } from 'astro:content';
import siteConfig from '../config/site';

export async function GET(context: any) {
  const posts = await getCollection('blog', ({ data }) => !data.draft);
  const sortedPosts = posts.sort((a, b) => b.data.pubDate.valueOf() - a.data.pubDate.valueOf());

  return rss({
    title: siteConfig.site.name || 'K-Pop Hangul | Learn Korean with K-Pop Hits',
    description: siteConfig.site.description || 'Learn Korean vocabulary, grammar, and pronunciation through top charting K-Pop song lyrics from Melon and Spotify.',
    site: siteConfig.site.url || 'https://kpop-hangul.github.io',
    items: sortedPosts.map((post) => ({
      title: post.data.title,
      pubDate: post.data.pubDate,
      description: post.data.description,
      link: `/blog/${post.slug}/`,
      categories: [post.data.difficulty || post.data.category, post.data.genre, ...(post.data.tags || [])].filter(Boolean),
    })),
    customData: `<language>en-US</language>`,
  });
}
