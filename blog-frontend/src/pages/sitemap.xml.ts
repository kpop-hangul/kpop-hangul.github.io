import { getCollection } from 'astro:content';
import siteConfig from '../config/site';
import { getCategorySlug, getGenreSlug, getArtistSlug } from '../utils/slug';

export async function GET(context: any) {
  const siteUrl = String(context.site || siteConfig.site.url || 'https://kpop-hangul.github.io').replace(/\/$/, '');
  const posts = await getCollection('blog', ({ data }) => !data.draft);

  const staticPages = [
    { url: '/', changefreq: 'daily', priority: '1.0' },
    { url: '/blog/', changefreq: 'daily', priority: '0.9' },
    { url: '/hangul/', changefreq: 'weekly', priority: '0.9' },
    { url: '/difficulty/', changefreq: 'weekly', priority: '0.8' },
    { url: '/difficulty/beginner/', changefreq: 'daily', priority: '0.8' },
    { url: '/difficulty/intermediate/', changefreq: 'daily', priority: '0.8' },
    { url: '/difficulty/advanced/', changefreq: 'daily', priority: '0.8' },
    { url: '/genres/', changefreq: 'weekly', priority: '0.8' },
    { url: '/artists/', changefreq: 'weekly', priority: '0.8' },
    { url: '/gallery/', changefreq: 'weekly', priority: '0.8' },
    { url: '/categories/', changefreq: 'weekly', priority: '0.8' },
    { url: '/search/', changefreq: 'weekly', priority: '0.7' },
    { url: '/about/', changefreq: 'monthly', priority: '0.7' },
    { url: '/privacy-policy/', changefreq: 'monthly', priority: '0.5' },
    { url: '/terms/', changefreq: 'monthly', priority: '0.5' },
    { url: '/contact/', changefreq: 'monthly', priority: '0.6' },
  ];

  const genrePages = [...new Set(posts.map(post => getGenreSlug(post.data.genre)))].filter(Boolean).map(slug => ({
    url: `/genres/${encodeURIComponent(slug)}/`,
    changefreq: 'weekly',
    priority: '0.8',
  }));

  const artistPages = [...new Set(posts.map(post => getArtistSlug(post.data.artist)))].filter(Boolean).map(slug => ({
    url: `/artists/${encodeURIComponent(slug)}/`,
    changefreq: 'weekly',
    priority: '0.8',
  }));

  const categoryPages = [...new Set(posts.map(post => getCategorySlug(post.data.category)))].filter(Boolean).map(slug => ({
    url: `/categories/${encodeURIComponent(slug)}/`,
    changefreq: 'weekly',
    priority: '0.8',
  }));

  const postPages = posts.map(post => ({
    url: `/blog/${post.slug}/`,
    lastmod: (post.data.updatedDate || post.data.pubDate).toISOString().split('T')[0],
    changefreq: 'weekly',
    priority: post.data.featured ? '0.9' : '0.8',
  }));

  const dynamicTaxonomyPages = [...genrePages, ...artistPages, ...categoryPages];

  const allUrls = [
    ...staticPages.map(page => `
    <url>
      <loc>${siteUrl}${page.url}</loc>
      <changefreq>${page.changefreq}</changefreq>
      <priority>${page.priority}</priority>
    </url>`),
    ...dynamicTaxonomyPages.map(page => `
    <url>
      <loc>${siteUrl}${page.url}</loc>
      <changefreq>${page.changefreq}</changefreq>
      <priority>${page.priority}</priority>
    </url>`),
    ...postPages.map(page => `
    <url>
      <loc>${siteUrl}${page.url}</loc>
      <lastmod>${page.lastmod}</lastmod>
      <changefreq>${page.changefreq}</changefreq>
      <priority>${page.priority}</priority>
    </url>`),
  ];

  const sitemapXml = `<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  ${allUrls.join('\n')}
</urlset>`.trim();

  return new Response(sitemapXml, {
    headers: {
      'Content-Type': 'application/xml; charset=utf-8',
    },
  });
}
