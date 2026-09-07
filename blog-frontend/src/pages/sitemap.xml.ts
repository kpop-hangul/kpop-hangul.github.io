import { getCollection } from 'astro:content';

export async function GET(context: any) {
  const siteUrl = String(context.site || 'https://absianp.github.io').replace(/\/$/, '');
  const posts = await getCollection('blog', ({ data }) => !data.draft);

  const staticPages = [
    { url: '/', changefreq: 'daily', priority: '1.0' },
    { url: '/blog/', changefreq: 'daily', priority: '0.9' },
    { url: '/about/', changefreq: 'monthly', priority: '0.7' },
    { url: '/privacy-policy/', changefreq: 'monthly', priority: '0.5' },
    { url: '/terms/', changefreq: 'monthly', priority: '0.5' },
    { url: '/contact/', changefreq: 'monthly', priority: '0.6' },
    { url: '/categories/ai-productivity/', changefreq: 'weekly', priority: '0.8' },
    { url: '/categories/tech-dev/', changefreq: 'weekly', priority: '0.8' },
    { url: '/categories/side-income/', changefreq: 'weekly', priority: '0.8' },
  ];

  const postPages = posts.map(post => ({
    url: `/blog/${post.slug}/`,
    lastmod: (post.data.updatedDate || post.data.pubDate).toISOString().split('T')[0],
    changefreq: 'weekly',
    priority: post.data.featured ? '0.9' : '0.8',
  }));

  const allUrls = [
    ...staticPages.map(page => `
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
