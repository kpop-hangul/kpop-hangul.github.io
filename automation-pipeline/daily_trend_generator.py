"""Compatibility entry point; K-Pop lessons always enter human review."""
from daily_kpop_pipeline import run_daily_pipeline

def generate_trend_post(keyword=None):
    return run_daily_pipeline(count=1)

if __name__ == "__main__":
    generate_trend_post()
