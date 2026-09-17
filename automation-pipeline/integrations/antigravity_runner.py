"""Compatibility import for existing callers; all generation now uses GPT."""
from integrations.gpt_runner import GPTRunner

AntigravityRunner = GPTRunner
