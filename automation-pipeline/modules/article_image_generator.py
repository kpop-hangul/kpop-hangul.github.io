"""GPT body illustrations; no deterministic SVG fallback."""
from modules.gpt_images import generate_body_images

def generate_and_integrate_article_images(article, slug, output_dir=None, site_prefix=None):
    return generate_body_images(article, slug, output_dir)
