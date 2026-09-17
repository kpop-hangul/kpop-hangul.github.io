import os
import json
import re
from functools import wraps
from uuid import uuid4
from modules.atomic_storage import atomic_json, file_lock

def locked(method):
    @wraps(method)
    def invoke(self, *args, **kwargs):
        with file_lock(self.queue_file + ".publication"), file_lock(self.queue_file):
            return method(self, *args, **kwargs)
    return invoke
from datetime import datetime
from typing import Dict, Any, List, Optional

class DraftApprovalQueue:
    """
    4시간마다 생성된 아티클 초안과 GPT 심층 감수 보고서를
    지속적으로 누적 관리하는 발행 대기 큐 모듈 (HITL 관리 시스템)
    """

    def __init__(self, queue_file: Optional[str] = None):
        if queue_file:
            path = os.path.abspath(queue_file)
            if os.path.isdir(path):
                pipeline = path if os.path.basename(path) == "automation-pipeline" else os.path.join(path, "automation-pipeline")
                self.queue_file = os.path.join(pipeline, "data", "draft_queue.json")
            else:
                self.queue_file = path
        else:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            self.queue_file = os.path.join(base_dir, "data", "draft_queue.json")

    def _load_data(self):
        if not os.path.exists(self.queue_file):
            return []
        with open(self.queue_file, encoding="utf-8") as handle:
            data = json.load(handle)
        if not isinstance(data, list) or any(not isinstance(d, dict) for d in data):
            raise ValueError("Invalid draft queue; preserve the file and repair it before writing")
        return data

    def _save_data(self, data):
        try:
            atomic_json(self.queue_file, data)
            return True
        except OSError:
            return False

    @locked
    def add_draft(
        self,
        article: Dict[str, Any],
        review_or_topic: Dict[str, Any],
        third_arg: Optional[Dict[str, Any]] = None,
        topic: Optional[Dict[str, Any]] = None,
        existing_slug: Optional[str] = None
    ) -> str:
        """
        초안 및 감수 보고서를 큐에 추가.
        (article, review, topic) 및 (article, topic, review) 호출 방식 모두 지원.
        """
        if "total_score" in review_or_topic:
            review_report = review_or_topic
            actual_topic = third_arg or topic or {}
        else:
            actual_topic = review_or_topic
            review_report = third_arg or {}

        data = self._load_data()
        now = datetime.now()
        title = article.get("title", actual_topic.get("title", "untitled"))
        slug_seed = re.sub(r"[^a-zA-Z0-9가-힣]", "", title)[:10] or "post"
        draft_id = f"draft_{now.strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:8]}"

        human_edit_points = (
            review_report.get("human_edit_points")
            or article.get("human_edit_points")
            or []
        )

        entry = {
            "draft_id": draft_id,
            "title": title,
            "category": article.get("category", actual_topic.get("category", "")),
            "existing_slug": existing_slug or article.get("existing_slug") or actual_topic.get("existing_slug"),
            "created_at": now.strftime("%Y-%m-%d %H:%M:%S"),
            "status": "pending_review",  # pending_review, approved, rejected, published
            "topic": actual_topic,
            "article": article,
            "review": review_report,
            "review_report": review_report,
            "human_edit_points": human_edit_points,
            "change_history": [],
            "published_at": None,
            "post_slug": None,
            "published_url": None,
            "rejected_at": None,
            "rejection_reason": None
        }

        data.append(entry)
        if not self._save_data(data):
            raise OSError("초안 큐 저장 실패")
        print(f"📥 [DraftQueue] 신규 초안 대기 큐 등록 완료: {draft_id} (제목: {title[:25]}...)")
        return draft_id

    @locked
    def update_draft_content(
        self,
        draft_id: str,
        new_article: Dict[str, Any],
        change_summary: Optional[str] = None,
        new_review: Optional[Dict[str, Any]] = None
    ) -> bool:
        """대기 큐에 있는 초안 본문/내용을 사람이 직접 수정/피드백 반영한 내용으로 업데이트"""
        data = self._load_data()
        resolved = self._resolve(data, draft_id)
        target = resolved.get("draft_id") if resolved else None
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        for d in data:
            if target and d.get("draft_id") == target:
                if d.get("status") == "published":
                    return False
                d["status"] = "pending_review"
                d.pop("approved_at", None)
                d["article"] = {**d.get("article", {}), **new_article}
                if "title" in new_article and new_article["title"].strip():
                    d["title"] = new_article["title"].strip()
                if "category" in new_article and new_article["category"].strip():
                    d["category"] = new_article["category"].strip()

                d["updated_at"] = now_str
                if change_summary:
                    d["change_summary"] = change_summary
                    if "change_history" not in d or not isinstance(d["change_history"], list):
                        d["change_history"] = []
                    d["change_history"].append({
                        "timestamp": now_str,
                        "summary": change_summary
                    })

                # 남은 human_edit_points 갱신
                body = new_article.get("markdown_content", "")
                markers = re.findall(r"(\[(?:💡|🔍)[^\]\n]+\])", body)
                d["human_edit_points"] = [
                    {"index": i, "marker": m, "recommendation": "수정/확인 필요"}
                    for i, m in enumerate(markers, 1)
                ]

                review = new_review or {"total_score": 0, "verdict": "REVIEW_REQUIRED", "is_approved": False,
                                        "review_status": "edited_requires_review", "summary_for_user": "본문 수정 후 재검토 필요"}
                d["review"] = review
                d["review_report"] = review

                return self._save_data(data)
        return False


    def list_pending(self) -> List[Dict[str, Any]]:
        """승인 대기(pending_review) 상태인 초안 목록 반환 (최신순)"""
        data = self._load_data()
        pending = [d for d in data if d.get("status") == "pending_review"]
        pending.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return pending

    def list_all(self, limit: int = 50) -> List[Dict[str, Any]]:
        """전체 초안 목록 반환 (최신순)"""
        data = self._load_data()
        data.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return data[:limit]

    @staticmethod
    def _resolve(data, draft_id):
        target = draft_id.strip()
        if not target:
            return None
        exact = [d for d in data if d.get("draft_id") == target]
        matches = exact or [d for d in data if target in d.get("draft_id", "")]
        if len(matches) > 1:
            raise ValueError("Ambiguous draft ID; use the complete ID")
        return matches[0] if matches else None

    def get_draft(self, draft_id):
        return self._resolve(self._load_data(), draft_id)

    @locked
    def mark_approved(self, draft_id: str) -> bool:
        """초안 승인 처리"""
        data = self._load_data()
        resolved = self._resolve(data, draft_id)
        target = resolved.get("draft_id") if resolved else None
        for d in data:
            if target and d.get("draft_id") == target:
                d["status"] = "approved"
                d["approved_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                return self._save_data(data)
        return False

    @locked
    def mark_published(self, draft_id: str, post_slug: str, published_url: Optional[str] = None) -> bool:
        """초안 발행 완료 처리 (URL 기록 지원)"""
        data = self._load_data()
        resolved = self._resolve(data, draft_id)
        target = resolved.get("draft_id") if resolved else None
        for d in data:
            if target and d.get("draft_id") == target:
                d["status"] = "published"
                d["published_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                d["post_slug"] = post_slug
                if published_url:
                    d["published_url"] = published_url
                return self._save_data(data)
        return False

    @locked
    def mark_rejected(self, draft_id: str, reason: str = "") -> bool:
        """초안 반려/보류 처리"""
        data = self._load_data()
        resolved = self._resolve(data, draft_id)
        target = resolved.get("draft_id") if resolved else None
        for d in data:
            if target and d.get("draft_id") == target:
                d["status"] = "rejected"
                d["rejected_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                d["rejection_reason"] = reason
                return self._save_data(data)
        return False


def serialize_publication(function):
    """Hold the queue mutation boundary until publishing the captured revision ends."""
    @wraps(function)
    def invoke(*args, **kwargs):
        # Resolve in the caller's module so its queue path/configuration is respected.
        queue = function.__globals__["DraftApprovalQueue"]()
        with file_lock(queue.queue_file + ".publication"):
            return function(*args, **kwargs)
    return invoke
