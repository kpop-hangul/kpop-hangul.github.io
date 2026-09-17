# GPT agent configuration

Default configuration, updated 2026-09-17.

| Work | Default |
| --- | --- |
| Planning, keywords, writing, rewriting, editorial review | `gpt-6-astra`, high reasoning |
| Thumbnail and body illustrations | Codex native GPT image generation; GPT orchestrator `gpt-6-astra`, medium reasoning |
| Images per draft | One thumbnail and two contextual body images |
| Generation engine | Authenticated `codex exec` (`codex_cli`) |
| Publication | Explicit human approval, then Git commit/push |

## Authentication and configuration

Install Codex CLI and run `codex login` as the Linux user running the services. This installation uses its ChatGPT login; no OpenAI API key is needed. Native image generation uses the image model managed by Codex and consumes the account's Codex allowance. We do not extract login credentials or send them to GitHub Actions.

Runtime defaults live in `automation-pipeline/config/config.yaml`. Root `blog.config.json` branding is merged into those settings; its `ai.provider` and `ai.model` override the corresponding text engine defaults. The starter installer writes both consistently. The legacy `AntigravityRunner` import is a compatibility alias for `GPTRunner`; it does not invoke `agy`.

## Draft lifecycle

1. GPT generates the article.
2. GPT generates three raster images from the title and body context. A content identity and file hashes allow retries to reuse valid images. Changed content receives a new image set.
3. GPT provides editorial advice and the article enters the review queue. Its score never counts as human approval.
4. Telegram previews the images and text for review. Explicit approval publishes the article and only its referenced image assets.

If text or image generation fails, the workflow reports failure instead of silently switching providers or creating an SVG placeholder. Failed publication remains retryable; K-Pop success records are written only after Git publication succeeds. Queue writes are atomic and locked across processes. Editing a queued draft clears its previous approval.

The automatic CLI mode creates review drafts. `--approve` on automatic generation does not bypass review. The legacy K-Pop `manage_kpop.py images` command now queues image updates for approval.

## Runtime and verification

Scheduled generation runs on the authenticated local systemd host. The GitHub agent workflow runs offline checks only; existing site deployment workflows still build on an authorized push. Each live site has its own Python environment; Golden Life and K-Pop use their private `.venv` through the existing `venv` entry point.

```bash
cd automation-pipeline
venv/bin/python3 -m unittest discover -s tests -v
cd ../blog-frontend
ASTRO_TELEMETRY_DISABLED=1 npm run build
```

Migration verification included offline approval/concurrency/asset/publication checks, all three Astro builds, starter generation, and a real GPT article with three images and editorial review saved to an isolated test queue. The test article was not published.

Existing published posts and their images are unchanged. Existing legacy drafts may retain their original images until rewritten; newly generated or rewritten drafts use the GPT defaults.
