import os
import json
import re
from datetime import datetime
from typing import Dict, Any, List, Optional

class DraftApprovalQueue:
    """
    4시간마다 생성된 아티클 초안과 Gemini 3.1 Pro 심층 감수 보고서를
    지속적으로 누적 관리하는 발행 대기 큐 모듈 (HITL 관리 시스템)
    """

    def __init__(self, queue_file: Optional[str] = None):
        if queue_file:
            self.queue_file = os.path.abspath(queue_file)
        else:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            self.queue_file = os.path.join(base_dir, "data", "draft_queue.json")

    def _load_data(self) -> List[Dict[str, Any]]:
        if not os.path.exists(self.queue_file):
            return []
        try:
            with open(self.queue_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, list) else []
        except Exception as e:
            print(f"⚠️ [DraftQueue] 큐 로드 오류: {e}")
            return []

    def _save_data(self, data: List[Dict[str, Any]]) -> bool:
        try:
            os.makedirs(os.path.dirname(self.queue_file), exist_ok=True)
            with open(self.queue_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            print(f"❌ [DraftQueue] 큐 저장 실패: {e}")
            return False

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
        draft_id = f"draft_{now.strftime('%Y%m%d_%H%M%S')}_{slug_seed}"

        entry = {
            "draft_id": draft_id,
            "title": title,
            "category": article.get("category", actual_topic.get("category", "")),
            "existing_slug": existing_slug or article.get("existing_slug") or actual_topic.get("existing_slug") or article.get("slug"),
            "created_at": now.strftime("%Y-%m-%d %H:%M:%S"),
            "status": "pending_review",  # pending_review, approved, rejected, published
            "topic": actual_topic,
            "article": article,
            "review": review_report,
            "review_report": review_report,
            "published_at": None,
            "post_slug": None,
            "published_url": None,
            "rejected_at": None,
            "rejection_reason": None
        }

        data.append(entry)
        self._save_data(data)
        print(f"📥 [DraftQueue] 신규 초안 대기 큐 등록 완료: {draft_id} (제목: {title[:25]}...)")
        return draft_id

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

    def get_draft(self, draft_id: str) -> Optional[Dict[str, Any]]:
        """ID로 초안 검색 (부분 일치 지원: 끝자리 또는 전체 ID)"""
        data = self._load_data()
        target = draft_id.strip()
        for d in data:
            if d.get("draft_id") == target:
                return d
        # 부분 일치 검색
        for d in data:
            if d.get("draft_id", "").endswith(target) or target in d.get("draft_id", ""):
                return d
        return None

    def mark_approved(self, draft_id: str) -> bool:
        """초안 승인 처리"""
        data = self._load_data()
        target = draft_id.strip()
        for d in data:
            if d.get("draft_id") == target or d.get("draft_id", "").endswith(target) or target in d.get("draft_id", ""):
                d["status"] = "approved"
                d["approved_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                return self._save_data(data)
        return False

    def mark_published(self, draft_id: str, post_slug: str, published_url: Optional[str] = None) -> bool:
        """초안 발행 완료 처리 (URL 기록 지원)"""
        data = self._load_data()
        target = draft_id.strip()
        for d in data:
            if d.get("draft_id") == target or d.get("draft_id", "").endswith(target) or target in d.get("draft_id", ""):
                d["status"] = "published"
                d["published_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                d["post_slug"] = post_slug
                if published_url:
                    d["published_url"] = published_url
                return self._save_data(data)
        return False

    def mark_rejected(self, draft_id: str, reason: str = "") -> bool:
        """초안 반려/보류 처리"""
        data = self._load_data()
        target = draft_id.strip()
        for d in data:
            if d.get("draft_id") == target or d.get("draft_id", "").endswith(target) or target in d.get("draft_id", ""):
                d["status"] = "rejected"
                d["rejected_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                d["rejection_reason"] = reason
                return self._save_data(data)
        return False
