import os
import json
import re
from typing import Dict, Any, Optional
from templates.prompt_templates import KPOP_CONTENT_WRITER_SYSTEM_PROMPT
from integrations.antigravity_runner import AntigravityRunner


from modules.content_validation import validate_article

class ContentGenerationError(RuntimeError):
    pass

class ContentWriter:
    """
    K-Pop Korean Language Content Writer Agent
    Uses GPT through the authenticated Codex CLI to generate
    rich, engaging, line-by-line Korean song learning lessons in English.
    """

    def __init__(self, config: Dict[str, Any], api_key: Optional[str] = None):
        self.config = config
        self.api_key = None  # Retained constructor compatibility; Codex login supplies authentication.
        self.model_name = config.get("agent", {}).get("model_name", "gpt-6-astra")
        self.antigravity_runner = AntigravityRunner(config)

    def write_song_lesson(self, song_info: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generates a complete Korean learning lesson for a given K-Pop track.
        """
        artist = song_info.get("artist", "K-Pop Artist")
        title = song_info.get("title", "Hit Song")
        album = song_info.get("album", "")
        chart_source = song_info.get("chartSource", "Melon Top 100")
        chart_rank = song_info.get("rank", 1)
        genre = song_info.get("genre", "Dance & Pop")
        difficulty = song_info.get("difficulty", "Beginner")

        user_prompt = f"""
[K-Pop Track Details for Lesson Generation]
- Artist: {artist}
- Song Title: {title}
- Album: {album or 'Single'}
- Chart Source: {chart_source}
- Chart Rank: #{chart_rank}
- Suggested Genre: {genre}
- Suggested Korean Difficulty: {difficulty}

[Lesson Requirements]
1. Write 100% of instructions, explanations, and grammar guides in engaging, natural ENGLISH.
2. In 'Key Lyrics Breakdown', select the most memorable chorus/hook and provide the exact 3-line format:
   - **Hangul**: [Original Korean]
   - **Romanization**: [Revised Romanization]
   - **English Translation**: [Natural meaning + literal nuances]
3. Include a Markdown Vocabulary Table with 6-10 essential words.
4. Deep dive into 2 key grammar patterns found in the song lyrics with formulas and 2 everyday example sentences.
5. Explain pronunciation secrets (batchim linking, tense consonants) and cultural slang/metaphors.
6. Provide an Interactive Quiz with 3 questions and answers hidden in an expandable `<details>` tag.
7. Include 3 structured Schema FAQs.

Ensure the output is strictly valid JSON matching the specified schema.
"""

        print(f"🎵 [KpopContentWriter] Generating lesson for '{artist} - {title}' ({chart_source} #{chart_rank})...")

        # 1. Try GPT / Codex CLI
        raw_output = self.antigravity_runner.generate_text(
            system_prompt=KPOP_CONTENT_WRITER_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            model_name=self.model_name, effort=self.config.get("agent", {}).get("effort", "high")
        )

        if raw_output:
            lesson_data = self._parse_json_response(raw_output)
            if isinstance(lesson_data, dict) and "markdown_content" in lesson_data:
                print(f"✅ [KpopContentWriter] Successfully generated lesson via GPT!")
                result = self._normalize_lesson(lesson_data, song_info)
                result.pop("human_approved", None)
                result["generation_status"] = "draft"
                result["requires_human_review"] = True
                return validate_article(result)

        raise ContentGenerationError("GPT did not return a valid lesson; no fallback article was created")

    def write_article(self, topic):
        return self.write_song_lesson(topic)

    def _parse_json_response(self, raw_text: Optional[str]) -> Optional[Dict[str, Any]]:
        if not raw_text:
            return None
        text = raw_text.strip()
        # Clean markdown code blocks
        if "```json" in text:
            m = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL)
            if m:
                text = m.group(1).strip()
        elif "```" in text:
            m = re.search(r"```\s*(.*?)\s*```", text, re.DOTALL)
            if m:
                text = m.group(1).strip()

        try:
            return json.loads(text)
        except Exception:
            # Try to find { ... }
            start = text.find("{")
            end = text.rfind("}")
            if start != -1 and end != -1:
                try:
                    return json.loads(text[start:end+1])
                except Exception:
                    pass
        return None

    def _normalize_lesson(self, data: Dict[str, Any], song_info: Dict[str, Any]) -> Dict[str, Any]:
        """Ensures all essential keys are present and standardized."""
        artist = data.get("artist") or song_info.get("artist", "K-Pop Artist")
        song_title = data.get("songTitle") or song_info.get("title", "Hit Song")
        diff = data.get("difficulty") or song_info.get("difficulty", "Beginner")
        genre = data.get("genre") or song_info.get("genre", "Dance & Pop")

        diff_map = {
            "Beginner": "Beginner (Level 1)",
            "Intermediate": "Intermediate (Level 2)",
            "Advanced": "Advanced (Level 3)"
        }
        category = diff_map.get(diff, "Beginner (Level 1)")

        data["artist"] = artist
        data["songTitle"] = song_title
        data["difficulty"] = diff
        data["category"] = category
        data["genre"] = genre
        data["chartRank"] = data.get("chartRank") or song_info.get("rank", 1)
        data["chartSource"] = data.get("chartSource") or song_info.get("chartSource", "Melon Top 100")
        data["album"] = data.get("album") or song_info.get("album", "")
        data["hangulTitle"] = data.get("hangulTitle", "")
        if not data.get("tags"):
            data["tags"] = [artist, song_title, "Learn Korean", "K-Pop Lyrics", diff, genre]

        return data

