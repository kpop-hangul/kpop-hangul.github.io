import { defineConfig } from 'astro/config';

export default defineConfig({
  site: 'https://absianp.github.io',
  base: '/kpop-hangul.github.io',
  trailingSlash: 'always',
  build: {
    format: 'directory',
  },
  markdown: {
    syntaxHighlight: 'shiki',
    shikiConfig: {
      theme: 'github-dark',
      wrap: true,
    },
  },
});
