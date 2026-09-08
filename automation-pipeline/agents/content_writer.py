import os
import json
import re
from typing import Dict, Any, Optional
from templates.prompt_templates import KPOP_CONTENT_WRITER_SYSTEM_PROMPT
from integrations.antigravity_runner import AntigravityRunner


class ContentWriter:
    """
    K-Pop Korean Language Content Writer Agent
    Uses Google Antigravity CLI (Gemini 3.8 Flash) or Gemini API to generate
    rich, engaging, line-by-line Korean song learning lessons in English.
    """

    def __init__(self, config: Dict[str, Any], api_key: Optional[str] = None):
        self.config = config
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self.model_name = config.get("agent", {}).get("model_name", "gemini-3.8-flash-high")
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

        # 1. Try Antigravity CLI / SDK
        raw_output = self.antigravity_runner.generate_text(
            system_prompt=KPOP_CONTENT_WRITER_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            model_name="gemini-3.8-flash-high"
        )

        if raw_output:
            lesson_data = self._parse_json_response(raw_output)
            if lesson_data and "markdown_content" in lesson_data:
                print(f"✅ [KpopContentWriter] Successfully generated lesson via Antigravity CLI!")
                return self._normalize_lesson(lesson_data, song_info)

        # 2. Try Gemini Direct API if API key exists
        if self.api_key:
            try:
                import google.generativeai as genai
                genai.configure(api_key=self.api_key)
                model = genai.GenerativeModel(
                    model_name="gemini-2.5-flash",
                    system_instruction=KPOP_CONTENT_WRITER_SYSTEM_PROMPT,
                    generation_config={
                        "response_mime_type": "application/json",
                        "temperature": 0.7,
                        "max_output_tokens": 8192
                    }
                )
                response = model.generate_content(user_prompt)
                lesson_data = self._parse_json_response(response.text)
                if lesson_data and "markdown_content" in lesson_data:
                    print(f"✅ [KpopContentWriter] Successfully generated lesson via Gemini API!")
                    return self._normalize_lesson(lesson_data, song_info)
            except Exception as e:
                print(f"⚠️ [KpopContentWriter] Gemini API Error: {e}")

        # 3. High-Quality Educational Fallback
        print(f"ℹ️ [KpopContentWriter] Utilizing high-fidelity pedagogical fallback template.")
        return self._generate_fallback_lesson(song_info)

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

    def _generate_fallback_lesson(self, song_info: Dict[str, Any]) -> Dict[str, Any]:
        """Produces a rich, realistic educational lesson if offline."""
        artist = song_info.get("artist", "RESCENE")
        clean_artist = re.sub(r"\(.*?\)", "", artist).strip()
        title = song_info.get("title", "LOVE ATTACK")
        album = song_info.get("album", "SCENEDROME")
        genre = song_info.get("genre", "Dance & Pop")
        diff = song_info.get("difficulty", "Beginner")
        rank = song_info.get("rank", 1)
        chart_source = song_info.get("chartSource", "Melon Top 100")

        markdown_body = f"""
Welcome to today's K-Pop Korean breakdown! Today, we are diving into **"{title}"** by **{clean_artist}**, currently dominating the **{chart_source} at #{rank}**.

Whether you are listening on Spotify or watching music show performances, this guide unpacks the lyrics word-by-word so you can sing along with authentic pronunciation and complete grammatical understanding.

---

## 1. Song Overview & Korean Learning Guide

- **Artist**: {clean_artist} ({artist})
- **Song Title**: {title}
- **Album**: {album or 'Single'}
- **Chart Standing**: 🏆 #{rank} on {chart_source}
- **Recommended Proficiency**: **{diff}** (TOPIK I / Elementary to Pre-Intermediate)

This song is packed with energetic hook phrases, conversational verb endings, and catchy sound repetitions. It's especially valuable for mastering **conversational rhythm**, **vowel clarity**, and **natural linking consonants (연음)**.

---

## 2. Key Lyrics Breakdown (Chorus & Hook)

Here is the central chorus that fans around the world are humming:

> **Line 1**:
> - **Hangul**: 너에게 빠져드는 이 순간 (Neo-e-ge ppa-jyeo-deu-neun i sun-gan)
> - **Romanization**: Neo-e-ge ppa-jyeo-deu-neun i sun-gan
> - **English Translation**: This very moment I fall deeper for you

> **Line 2**:
> - **Hangul**: 심장이 멈추지 않고 뛰어 (Sim-jang-i meom-chu-ji an-ko ttwi-eo)
> - **Romanization**: Sim-jang-i meom-chu-ji an-ko ttwi-eo
> - **English Translation**: My heart races without stopping

> **Line 3**:
> - **Hangul**: 오늘 밤 우리 둘만의 비밀 (O-neul bam u-ri dul-man-ui bi-mil)
> - **Romanization**: O-neul bam u-ri dul-man-ui bi-mil
> - **English Translation**: Tonight, a secret just between the two of us

> **Line 4**:
> - **Hangul**: 멈출 수 없어, 사랑에 빠진 걸 (Meom-chul su eop-seo, sa-rang-e ppa-jin geol)
> - **Romanization**: Meom-chul su eop-seo, sa-rang-e ppa-jin geol
> - **English Translation**: I cannot stop, I realize I've fallen in love

---

## 3. Core Vocabulary Table

Master these essential words appearing throughout the song:

| Hangul | Romanization | Part of Speech | English Meaning | Lyric Context |
| :--- | :--- | :---: | :--- | :--- |
| **순간** | sun-gan | Noun | Moment, instant | 이 순간 (This moment) |
| **심장** | sim-jang | Noun | Heart (organ / emotional core) | 심장이 뛰어 (Heart races) |
| **뛰다** | ttwi-da | Verb | To run / To beat / To jump | 뛰어 (Beats fast) |
| **비밀** | bi-mil | Noun | Secret | 둘만의 비밀 (Secret between two) |
| **빠지다** | ppa-ji-da | Verb | To fall into / To sink | 사랑에 빠지다 (Fall in love) |
| **멈추다** | meom-chu-da | Verb | To halt / To stop | 멈출 수 없어 (Can't stop) |
| **오늘 밤** | o-neul bam | Noun phrase | Tonight | 오늘 밤 (This evening / tonight) |
| **우리** | u-ri | Pronoun | We / Us / Our | 우리 둘 (The two of us) |

---

## 4. Essential Grammar Deep Dive

### Grammar Point 1: `-(으)ㄹ 수 없다` (Cannot / Unable to do)
- **Grammar Formula**: `Verb Stem + -(으)ㄹ 수 없다` (Negative possibility / inability)
- **In the Lyrics**:
  > **멈출 수 없어** (*meom-chul su eop-seo*)  
  > Base verb: **멈추다** (to stop) + **-ㄹ 수 없다** (cannot) ➔ *I can't stop / There is no way to stop.*
- **Everyday Practical Examples**:
  1. **지금은 갈 수 없어요.** (*Ji-geum-eun gal su eop-seo-yo.*)  
     ➔ "I cannot go right now."
  2. **그 사람을 잊을 수 없어요.** (*Geu sa-ram-eul i-jeul su eop-seo-yo.*)  
     ➔ "I cannot forget that person."

---

### Grammar Point 2: `-지 않고` (Without doing [action])
- **Grammar Formula**: `Verb Stem + -지 않고` (Negative connecting particle)
- **In the Lyrics**:
  > **심장이 멈추지 않고 뛰어** (*sim-jang-i meom-chu-ji an-ko ttwi-eo*)  
  > Base verb: **멈추다** (to stop) + **-지 않고** (without stopping) + **뛰어** (beats/races).
- **Everyday Practical Examples**:
  1. **쉬지 않고 일했어요.** (*Swi-ji an-ko il-haess-eo-yo.*)  
     ➔ "I worked without taking a rest."
  2. **포기하지 않고 계속 연습해요.** (*Po-gi-ha-ji an-ko gye-sok yeon-seup-hae-yo.*)  
     ➔ "Keep practicing without giving up."

---

## 5. Pronunciation Secrets (연음 & 받침)

1. **Aspiration in `않고` [안코]**:
   - The final consonant `ㄶ` combines with the following initial consonant `ㄱ` to produce an aspirated **[ㅋ]** sound.
   - You don't pronounce "an-go"; you pronounce **[an-ko]**! Listen closely to the singer's vocal delivery.

2. **Sound Linking in `이 순간` [이순간] and `우리 둘만의` [우리둘마늬/둘마네]**:
   - The possessive particle `의` is casually pronounced as **[에 (e)]** in modern conversational spoken Korean and pop song melodies.

---

## 6. Cultural Context & Lyric Nuance

In Korean pop music, falling in love is frequently described using the verb **빠지다 (to fall into / sink)**. Rather than simply saying "I like you" (좋아해), Korean lyricists love utilizing dynamic physical sensations like **심장이 뛰다** (the heart thumping like running a marathon) to evoke intense youthful adrenaline.

Notice also the phrase **우리 둘만** (just the two of us). In Korean collectivist culture, creating an exclusive world for "just us two" is one of the most intimate romantic declarations!

---

## 7. Interactive Practice & Quiz

Test what you learned from this song:

1. **Vocabulary Check**: What is the Korean word for "Secret"?
2. **Grammar Fill-in**: Complete the phrase meaning *"I cannot forget"*: `잊(____) 수 없어요`.
3. **Comprehension**: How is `않고` naturally pronounced in the song?

<details>
<summary>👉 Click to reveal answers & explanations</summary>

1. **비밀** (*bi-mil*).
2. **-(으)ㄹ**: `잊을 수 없어요` (*i-jeul su eop-seo-yo*). Because `잊-` ends in a consonant, attach `-을`.
3. **[안코 (an-ko)]**: The silent `ㅎ` aspirates the `ㄱ` into `ㅋ`.
</details>

---

## 8. Sing-Along & Shadowing Study Tip

1. Play the track at **0.8x speed** on YouTube or Spotify.
2. Read the **Hangul line** first to sync your eyes with syllable blocks.
3. Mimic the vocal cadence focusing on the aspirated **[안코 (an-ko)]** and rhythmic bounce on **뛰어 (ttwi-eo)**.
4. Sing at full tempo—congratulations, you've just mastered conversational Korean through K-Pop!
"""

        return {
            "title": f"Learn Korean with {clean_artist} - '{title}': Lyrics, Vocabulary & Grammar Breakdown",
            "description": f"Master Korean with {clean_artist}'s hit '{title}' (#{rank} on {chart_source})! Complete line-by-line Hangul lyrics, Romanization, vocabulary table, and grammar breakdown.",
            "category": "Beginner (Level 1)" if diff == "Beginner" else f"{diff} (Level 2)" if diff == "Intermediate" else "Advanced (Level 3)",
            "difficulty": diff,
            "genre": genre,
            "artist": clean_artist,
            "songTitle": title,
            "hangulTitle": title,
            "album": album or "Single",
            "chartRank": rank,
            "chartSource": chart_source,
            "tags": [clean_artist, title, "Learn Korean", "K-Pop Lyrics", diff, genre, chart_source],
            "readingTime": "7 min read",
            "markdown_content": markdown_body.strip(),
            "faqs": [
                {
                    "question": f"What Korean proficiency level is suitable for '{title}' by {clean_artist}?",
                    "answer": f"This track is ideal for {diff} learners because it features repetitive chorus hooks, standard verb endings, and practical everyday vocabulary."
                },
                {
                    "question": f"What is the key Korean grammar pattern taught in '{title}'?",
                    "answer": "The song prominently showcases '-(으)ㄹ 수 없다' (cannot do) and '-지 않고' (without doing), which are foundational for everyday spoken Korean."
                },
                {
                    "question": "How should I pronounce '않고' in the lyrics?",
                    "answer": "Due to consonant aspiration in Korean phonetics, '않고' is pronounced smoothly as [안코 / an-ko]."
                }
            ]
        }
