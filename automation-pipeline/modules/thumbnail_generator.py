"""GPT thumbnail entry point (keeps the legacy import API)."""
from modules.gpt_images import generate_thumbnail

def generate_thumbnail_for_post(post_data, output_dir=None):
    return generate_thumbnail(post_data, output_dir)
