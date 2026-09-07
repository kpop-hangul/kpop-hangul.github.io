import { defineConfig } from 'astro/config';

export default defineConfig({
  site: 'https://kpop-hangul.github.io',
  base: '/',
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
