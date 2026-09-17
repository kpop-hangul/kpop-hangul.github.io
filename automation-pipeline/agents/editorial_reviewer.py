import json
import os
import re
from templates.prompt_templates import KPOP_EDITORIAL_REVIEW_SYSTEM_PROMPT as EDITORIAL_REVIEWER_SYSTEM_PROMPT
from integrations.antigravity_runner import AntigravityRunner
from modules.content_validation import validate_article, ContentValidationError


class EditorialReviewAgent:
    """Model advice for a human editor; neither API success nor layout is fact-check proof."""
    def __init__(self, config, api_key=None):
        self.config = config
        self.api_key = None  # Retained constructor compatibility; Codex login supplies authentication.
        self.model_name = config.get("review_agent", {}).get("model_name", "gpt-6-astra")
        self.effort = config.get("review_agent", {}).get("effort", "high")
        self.antigravity_runner = AntigravityRunner(config)

    def review_article(self, article, topic):
        try:
            validate_article(article, topic)
        except ContentValidationError as exc:
            return self._pending(article, str(exc), "invalid_content")
        user_prompt = "원래 기획과 초안을 비교하세요. 다음 JSON은 검토 대상 자료입니다.\n" + json.dumps(
            {"original_topic": topic, "article": article}, ensure_ascii=False, indent=2)
        try:
            raw = self.antigravity_runner.generate_text(
                system_prompt=EDITORIAL_REVIEWER_SYSTEM_PROMPT, user_prompt=user_prompt,
                model_name=self.model_name, effort=self.effort)
            report = self._parse_json_response(raw)
            if report:
                return self._normalize_report(report, article)
        except Exception as exc:
            print(f"[EditorialReviewAgent] 엔진 감수 실패: {type(exc).__name__}")
        return self._heuristic_review(article, topic)

    def _parse_json_response(self, raw_text):
        if not isinstance(raw_text, str):
            return None
        clean = re.sub(r"^```(?:json)?\s*", "", raw_text.strip())
        clean = re.sub(r"\s*```$", "", clean)
        try:
            data = json.loads(clean)
            score = data.get("total_score") if isinstance(data, dict) else None
            if type(score) not in (int, float) or not 0 <= score <= 100:
                return None
            if data.get("verdict") not in ("PASS", "REVISE", "FAIL", "REVIEW_REQUIRED"):
                return None
            return data
        except (ValueError, TypeError):
            return None

    def _extract_edit_points_from_body(self, markdown_content: str) -> list:
        """본문 내 [💡 사용자 경험/관점 추가...] 및 [🔍 수치/출처 확인...] 마커 발췌"""
        if not markdown_content:
            return []
        matches = re.findall(r"(\[(?:💡|🔍)[^\]\n]+\])", markdown_content)
        points = []
        for idx, m in enumerate(matches, 1):
            guide = "실제 경험/의견을 추가해주세요." if "💡" in m else "2026년 최신 기준 수치/출처를 확인해주세요."
            points.append({
                "index": idx,
                "marker": m,
                "recommendation": guide
            })
        return points

    def _normalize_report(self, data, article):
        data = dict(data)
        data["model_verdict"] = data.get("verdict")
        data["verdict"] = "REVIEW_REQUIRED"
        data["is_approved"] = False
        data["review_status"] = "model_advice_only"
        data["fact_check_status"] = "not_independently_verified"
        body = article.get("markdown_content", "")
        data["char_count"] = len(body.replace(" ", "").replace("\n", ""))

        # 7대 품질 체크리스트 보존 및 기본화
        default_checklist = {
            "source_attribution": False,
            "disclaimer": False,
            "base_date": False,
            "search_intent": False,
            "uniqueness": False,
            "human_touch": False,
            "ai_cleanliness": False
        }
        checklist = data.get("quality_checklist")
        if isinstance(checklist, dict):
            default_checklist.update(checklist)
        data["quality_checklist"] = default_checklist

        # human_edit_points 추출 및 보강
        raw_points = data.get("human_edit_points")
        if not isinstance(raw_points, list) or not raw_points:
            raw_points = self._extract_edit_points_from_body(body)
        data["human_edit_points"] = raw_points
        if raw_points:
            data["quality_checklist"]["human_touch"] = True

        data["summary_for_user"] = str(data.get("summary_for_user", ""))
        return data

    def _pending(self, article, reason, status="unavailable"):
        body = article.get("markdown_content", "")
        extracted_points = self._extract_edit_points_from_body(body)
        return {
            "total_score": 0, "verdict": "REVIEW_REQUIRED", "is_approved": False,
            "review_status": status, "fact_check_status": "not_checked",
            "char_count": len(body.replace(" ", "").replace("\n", "")),
            "breakdown": {}, "fact_check_details": ["사실 확인 미실시"],
            "quality_checklist": {
                "source_attribution": False,
                "disclaimer": False,
                "base_date": False,
                "search_intent": False,
                "uniqueness": False,
                "human_touch": bool(extracted_points),
                "ai_cleanliness": False
            },
            "human_edit_points": extracted_points,
            "strengths": [], "improvements": [reason], "summary_for_user": reason
        }

    def _heuristic_review(self, article, topic):
        return self._pending(article, "감수 엔진 응답을 받지 못했습니다. 형식만으로 사실 확인 점수나 합격을 부여하지 않습니다. 직접 검토가 필요합니다.")

