"""Local format/regression lint only. It cannot certify AdSense or factual accuracy."""
import re
from modules.content_validation import validate_article, ContentValidationError


class PolicyInspector:
    def __init__(self, config):
        self.config = config

    def inspect_article(self, article):
        content = article.get("markdown_content", "") if isinstance(article, dict) else ""
        improvements = ["공식 출처 및 날짜, 제목과 본문/FAQ의 일치, 독자에게 유용한 내용을 사람이 확인하세요."]
        try:
            validate_article(article)
            format_valid = True
        except ContentValidationError as exc:
            format_valid = False
            improvements.insert(0, str(exc))
        char_count = len(content.replace(" ", "").replace("\n", ""))
        return {"score": 0, "is_approved": False, "format_valid": format_valid,
                "char_count": char_count, "word_count": len(content.split()),
                "policy_risk": "Unknown", "fact_check_status": "not_checked",
                "strengths": [], "improvements": improvements,
                "summary": f"형식 사전 점검: {'정상' if format_valid else '수정 필요'}. {char_count}자. 정책/사실 확인 및 승인 평가는 미실시입니다."}
