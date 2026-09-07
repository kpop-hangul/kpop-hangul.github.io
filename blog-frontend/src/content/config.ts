import { defineCollection, z } from 'astro:content';

const blogCollection = defineCollection({
  type: 'content',
  schema: z.object({
    title: z.string(),
    description: z.string(),
    pubDate: z.coerce.date(),
    updatedDate: z.coerce.date().optional(),
    heroImage: z.string().optional().default('/images/default-hero.svg'),
    category: z.string().default('General'),
    tags: z.array(z.string()).default([]),
    author: z.string().default('앱시안 (absian)'),
    readingTime: z.string().optional().default('5 min read'),
    featured: z.boolean().optional().default(false),
    draft: z.boolean().optional().default(false),
    faqs: z.array(
      z.object({
        question: z.string(),
        answer: z.string(),
      })
    ).optional(),
  }),
});

export const collections = {
  blog: blogCollection,
};
