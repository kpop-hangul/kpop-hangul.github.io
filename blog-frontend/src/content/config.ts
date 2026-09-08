import { defineCollection, z } from 'astro:content';

const blogCollection = defineCollection({
  type: 'content',
  schema: z.object({
    title: z.string(),
    description: z.string(),
    pubDate: z.coerce.date(),
    updatedDate: z.coerce.date().optional(),
    heroImage: z.string().optional().default('/images/default-hero.svg'),
    category: z.string().default('Beginner (Level 1)'),
    difficulty: z.enum(['Beginner', 'Intermediate', 'Advanced']).default('Beginner'),
    genre: z.string().default('Dance & Pop'),
    artist: z.string().default('Various Artists'),
    songTitle: z.string(),
    hangulTitle: z.string().optional().default(''),
    album: z.string().optional().default(''),
    chartRank: z.number().optional(),
    chartSource: z.string().optional().default('Melon Top 100'),
    youtubeId: z.string().optional().default(''),
    tags: z.array(z.string()).default([]),
    author: z.string().default('K-Pop Hangul Team'),
    readingTime: z.string().optional().default('6 min read'),
    featured: z.boolean().optional().default(false),
    draft: z.boolean().optional().default(false),
    faqs: z.array(
      z.object({
        question: z.string(),
        answer: z.string(),
      })
    ).optional().default([]),
  }),
});

export const collections = {
  blog: blogCollection,
};

