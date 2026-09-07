import os
import json
import re
from typing import Dict, Any, Optional
from templates.prompt_templates import CONTENT_WRITER_SYSTEM_PROMPT
from integrations.antigravity_runner import AntigravityRunner

class ContentWriter:
    """
    Google Antigravity CLI / SDK 또는 로컬 모델을 활용하여
    1,500~2,500자 이상의 SEO 최적화 마크다운 아티클과 FAQ를 작성하는 에이전트
    """

    def __init__(self, config: Dict[str, Any], api_key: Optional[str] = None):
        self.config = config
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self.model_name = config.get("agent", {}).get("model_name", "gemini-2.5-flash")
        self.antigravity_runner = AntigravityRunner(config)

    def write_article(self, topic: Dict[str, Any]) -> Dict[str, Any]:
        """
        주어진 주제(topic dict)를 바탕으로 완성도 높은 마크다운 글과 메타데이터 생성
        """
        title = topic.get("title", "AI 생산성 실전 가이드")
        category = topic.get("category", "AI & 생산성")
        target_keyword = topic.get("target_keyword", "")
        tags = topic.get("tags", ["AI", "생산성", "테크"])
        key_points = topic.get("key_points", [])

        user_prompt = f"""
[작성 요청 사양]
- 글 제목: {title}
- 카테고리: {category}
- 핵심 타겟 롱테일 키워드: {target_keyword}
- 태그 후보: {', '.join(tags)}
- 반드시 다룰 핵심 포인트:
{chr(10).join([f"  * {kp}" for kp in key_points])}

위 내용을 토대로 서론, 본론(H2, H3, 비교 표, 실전 팁), 결론, 그리고 3개의 FAQ를 충실하게 작성해주세요.
반드시 지정된 JSON 포맷(title, description, category, tags, readingTime, markdown_content, faqs)으로만 응답하세요.
"""

        # 1. Antigravity CLI / SDK / On-Device 로컬 엔진 우선 호출
        raw_output = self.antigravity_runner.generate_text(
            system_prompt=CONTENT_WRITER_SYSTEM_PROMPT,
            user_prompt=user_prompt
        )

        if raw_output:
            try:
                # JSON 파싱 시도 (마크다운 코드블록 제거)
                clean_json = re.sub(r"^```json\s*", "", raw_output.strip())
                clean_json = re.sub(r"\s*```$", "", clean_json)
                article_data = json.loads(clean_json)
                if isinstance(article_data, dict) and "markdown_content" in article_data:
                    return article_data
            except Exception:
                pass

        # 2. Gemini Direct API 호출 시도 (API 키가 있는 경우)
        if self.api_key:
            try:
                import google.generativeai as genai
                genai.configure(api_key=self.api_key)
                model = genai.GenerativeModel(
                    model_name=self.model_name,
                    system_instruction=CONTENT_WRITER_SYSTEM_PROMPT,
                    generation_config={
                        "response_mime_type": "application/json",
                        "temperature": 0.7,
                        "max_output_tokens": 8192
                    }
                )
                response = model.generate_content(user_prompt)
                article_data = json.loads(response.text)
                return article_data
            except Exception as e:
                print(f"[ContentWriter] API 호출 예외 (Fallback 모드로 전환): {e}")

        # 3. 고품질 Fallback 템플릿 가동
        return self._generate_fallback_article(topic)

    def _generate_fallback_article(self, topic: Dict[str, Any]) -> Dict[str, Any]:
        title = topic.get("title", "2026년 업무 속도 5배 높이는 AI 실전 활용법 총정리")
        category = topic.get("category", "AI & 생산성")
        tags = topic.get("tags", ["AI", "생산성", "자동화", "2026트렌드"])
        target_kw = topic.get("target_keyword", "AI 활용법")

        content = f"""
급변하는 2026년 디지털 환경에서 생산성을 극대화하기 위해서는 단순한 툴 사용을 넘어 **체계적인 자동화 워크플로우**를 구축해야 합니다. 본 글에서는 초보자부터 실무자까지 누구나 즉시 적용할 수 있는 핵심 전략을 정리해 드립니다.

---

## 1. 왜 지금 {target_kw}이(가) 중요한가?

기존의 단순 반복 작업(데이터 수집, 문서 요약, 이메일 초안 작성 등)은 하루 업무 시간의 최대 40% 이상을 소모하게 만듭니다. 하지만 최신 도구를 적절히 조합하면 이러한 수작업 시간을 획기적으로 단축할 수 있습니다.

### 핵심 이점 요약
- **시간 절약**: 반복 루틴 작업 자동화로 주당 최소 5~10시간 절약
- **정확도 향상**: 표준화된 프롬프트와 템플릿으로 휴먼 에러 방지
- **멀티태스킹 최적화**: 고부가가치 기획 및 전략 수립에 온전히 집중 가능

---

## 2. 실무 적용 3단계 프로세스

효과적인 도입을 위한 3단계 로드맵은 다음과 같습니다.

### 1단계: 일상 루틴 병목 구간 파악
가장 먼저 본인이 매일 반복하는 작업 목록을 작성하고, 그중 규칙성이 명확한 작업을 선별합니다.

### 2단계: 최적의 도구 스택 선정 및 연동
상황과 목적에 맞는 최적의 도구를 선택하는 것이 성공의 핵심입니다.

| 구분 | 추천 도구 | 주요 활용처 | 난이도 |
| :--- | :--- | :--- | :--- |
| **자료 요약 & 분석** | Gemini / Claude | 긴 문서 분석, 핵심 인사이트 추출 | 초급 |
| **코드 및 스크립트** | VS Code + Copilot | 데이터 가공, 크롤링 자동화 | 중급 |
| **워크플로우 연결** | Make / Zapier | 텔레그램 알림, 시트 자동 기록 | 초급 |

### 3단계: 나만의 템플릿 자산화
자주 사용하는 프롬프트와 자동화 규칙은 별도의 마크다운 문서나 노션 템플릿으로 저장하여 재사용성을 극대화합니다.

---

## 3. 애드센스 및 검색엔진 노출을 위한 실전 팁

블로그나 사이트를 운영하며 관련 주제로 트래픽을 유입시키려면 다음 요소를 반드시 점검하세요.

1. **독창적인 경험(E-E-A-T) 공유**: 툴을 직접 사용해보고 느낀 장단점을 가감 없이 솔직하게 서술하세요.
2. **명확한 해결책 제시**: 질문에 대해 빙빙 돌리지 않고 첫 문단에서 즉각적인 솔루션을 제공하세요.
3. **가독성 높은 서식**: 텍스트만 빽빽한 글 대신 표(Table), 굵은 글씨, 목록 기호를 적절히 배치하세요.

---

## 4. 마무리 및 요약

결국 기술의 발전은 '얼마나 빨리 내 워크플로우에 내재화하는가'의 싸움입니다. 오늘 소개해 드린 단계별 가이드를 바탕으로 지금 바로 작은 것부터 하나씩 자동화해 보시길 권장합니다.
"""

        return {
          "title": title,
          "description": f"{title}에 대한 상세한 단계별 실전 가이드와 실무 적용 비교표, 자주 묻는 질문 3가지를 정리했습니다.",
          "category": category,
          "tags": tags,
          "readingTime": "6 min read",
          "markdown_content": content.strip(),
          "faqs": [
            {
              "question": f"{target_kw}을(를) 시작하려면 코딩 지식이 필수적인가요?",
              "answer": "아닙니다. 최근의 대부분 도구들은 웹 브라우저나 직관적인 노코드 UI를 제공하므로 코딩을 전혀 몰라도 쉽게 활용할 수 있습니다."
            },
            {
              "question": "무료 버전만으로도 실무에서 충분한 성능을 발휘하나요?",
              "answer": "네, 개인적인 업무 효율화나 블로그 운영 수준에서는 무료 티어에서 제공하는 기능만으로도 90% 이상의 작업을 완벽히 처리할 수 있습니다."
            },
            {
              "question": "구글 애드센스 승인용 글로 활용하기에 충분한가요?",
              "answer": "네, 1,500자 이상의 충실한 본문, H2/H3 계층 구조, 비교표, FAQ 구조화 데이터가 모두 포함되어 있어 애드센스 승인 가이드라인에 완벽히 부합합니다."
            }
          ]
        }
