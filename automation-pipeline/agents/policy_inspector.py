import re
from typing import Dict, Any, List

class PolicyInspector:
    """
    구글 애드센스 정책 위반 위험성 및 SEO 검색 품질을 사전 검토하는 감사 에이전트
    """

    # 애드센스 승인 거절 및 제재 유발 위험 키워드 목록
    FORBIDDEN_KEYWORDS = [
        "불법", "도박", "성인", "카지노", "마약", "해킹툴", "불법복제", "크랙다운",
        "음란", "선정성", "토렌트", "치트키", "무단배포"
    ]

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.min_target_words = config.get("content", {}).get("target_length_words", 1500)

    def inspect_article(self, article: Dict[str, Any]) -> Dict[str, Any]:
        """
        생성된 아티클의 SEO 점수, 글자 수, 구조화 수준 및 애드센스 정책 위험도를 다각도로 평가
        """
        title = article.get("title", "")
        description = article.get("description", "")
        content = article.get("markdown_content", "")
        tags = article.get("tags", [])
        faqs = article.get("faqs", [])

        # 1. 글자 수 및 단어 수 검사 (한글 기준 글자수 / 단어수)
        char_count = len(content.replace(" ", "").replace("\n", ""))
        word_count = len(content.split())

        score = 100
        strengths = []
        improvements = []
        policy_risk = "None"

        # 2. 분량 점수 평가
        if char_count >= 1500 or word_count >= 500:
            strengths.append(f"충분한 본문 분량 (한글 {char_count:,}자, {word_count}단어)")
        else:
            deduction = 20
            score -= deduction
            improvements.append(f"분량 부족: 현재 {char_count}자 (권장 1,500자 이상). 심층 팁 추가 권장")

        # 3. 구조화 평가 (H2, H3, 표, 리스트)
        h2_count = len(re.findall(r"^##\s+", content, re.MULTILINE))
        h3_count = len(re.findall(r"^###\s+", content, re.MULTILINE))
        has_table = "|" in content and "-|-" in content

        if h2_count >= 3:
            strengths.append(f"체계적인 H2 섹션 구조 ({h2_count}개)")
        else:
            score -= 10
            improvements.append("H2 헤딩 수가 적음 (최소 3개 이상 권장)")

        if has_table:
            strengths.append("비교 및 요약 표(Table) 포함으로 가독성 우수")
        else:
            score -= 5
            improvements.append("비교 분석 표(Table)를 추가하면 E-E-A-T 점수가 향상됩니다")

        # 4. Schema.org FAQ 평가
        if len(faqs) >= 3:
            strengths.append(f"구글 검색 스니펫용 FAQ {len(faqs)}개 완비")
        else:
            score -= 10
            improvements.append("FAQ 항목 3개 이상 필요")

        # 5. 메타 디스크립션 평가
        if 80 <= len(description) <= 200:
            strengths.append(f"적절한 메타 설명 길이 ({len(description)}자)")
        else:
            score -= 5
            improvements.append("메타 디스크립션 길이를 100~150자 사이로 조정 권장")

        # 6. 애드센스 금칙어 검사
        found_forbidden = [kw for kw in self.FORBIDDEN_KEYWORDS if kw in title or kw in content]
        if found_forbidden:
            score -= 40
            policy_risk = "High"
            improvements.append(f"애드센스 정책 위반 위험 키워드 발견: {', '.join(found_forbidden)}")
        else:
            strengths.append("애드센스 정책 준수 (위험 키워드 0건)")

        is_approved = score >= 80 and policy_risk == "None"

        summary = (
            f"✅ 품질 점수: {score}/100점 (승인: {'통과' if is_approved else '보류'})\n"
            f"📊 분량: {char_count:,}자 | 헤딩: {h2_count}개 | FAQ: {len(faqs)}개 | 정책 리스크: {policy_risk}"
        )

        return {
            "score": score,
            "is_approved": is_approved,
            "char_count": char_count,
            "word_count": word_count,
            "policy_risk": policy_risk,
            "strengths": strengths,
            "improvements": improvements,
            "summary": summary,
        }
