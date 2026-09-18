"""Human approval submits a commit; a separate reconciliation proves live success."""
from datetime import datetime

from modules.content_validation import validate_article, ContentValidationError
from modules.draft_queue import approval_is_current, article_review_token
from integrations.deployment_verifier import DeploymentVerifier


def submit(config, draft_id, queue, publisher_factory, *, human_approved=False, slug_factory=None, expected_review_token=None):
    draft = queue.get_draft(draft_id)
    if not draft:
        return False, "초안을 찾을 수 없습니다."
    if draft.get("status") == "published":
        return True, draft.get("published_url", "")
    if draft.get("status") in ("pushed", "deployment_pending"):
        return False, "배포 확인 대기: reconcile 명령으로 공개 글과 이미지를 확인하세요."
    if human_approved is not True or draft.get("status") not in ("pending_review", "approved"):
        return False, "검토 가능한 초안 본문과 출처에 대한 사람의 승인이 필요합니다."
    if expected_review_token is not None and expected_review_token != article_review_token(draft.get("article", {})):
        return False, "초안 버전이 바뀌었습니다. /queue에서 최신 본문을 검토하고 승인하세요."
    try:
        validate_article(draft.get("article", {}), draft.get("topic", {}))
        if draft.get("approved_fingerprint") and not approval_is_current(draft):
            return False, "승인 이후 초안이 변경되었습니다. 수정 기능으로 저장하고 다시 검토하세요."
        if not queue.mark_approved(draft["draft_id"]):
            return False, "승인 상태 저장 실패. 발행하지 않았습니다."
        draft = queue.get_draft(draft["draft_id"])
        _prepare(config, draft, queue, publisher_factory, slug_factory)
        return False, "배포 확인 대기: Push가 완료되었습니다. reconcile 명령으로 Pages·공개 글·이미지를 확인하세요."
    except ContentValidationError as exc:
        return False, f"발행 전 내용 점검 실패: {exc}"
    except Exception as exc:
        # Do not expose credential-bearing Git/HTTP exception text.
        return False, f"발행 준비 중단 ({type(exc).__name__}). 승인·배포 기록을 유지했습니다. 저장소 상태 확인 후 재시도하세요."


def _prepare(config, draft, queue, publisher_factory, slug_factory=None):
    if not approval_is_current(draft):
        raise PermissionError("Approval does not match this revision")
    publisher = publisher_factory(config)
    record = draft.get("publication", {})
    if not record:
        article = draft["article"]
        existing = draft.get("existing_slug") or article.get("existing_slug")
        # Legacy K-Pop queues also used existing_slug for a new lesson.
        is_update = bool(existing and publisher._path(existing).is_file())
        slug = existing if is_update else article.get("slug") or (slug_factory(article) if slug_factory else publisher.generate_slug(article["title"], article["category"]))
        record = {"slug": slug, "is_update": is_update, "revision": draft["approved_fingerprint"],
                  "url": config.get("site", {}).get("url", "").rstrip("/") + f"/blog/{slug}/",
                  "created_at": datetime.now().isoformat()}
    if record.get("revision") != draft["approved_fingerprint"]:
        raise PermissionError("Publication belongs to another revision")

    def persist(value, status):
        if not queue.record_publication(draft["draft_id"], value, status):
            raise OSError("Could not persist publication progress")

    persist(record, "approved" if not record.get("pushed_at") else "deployment_pending")
    return publisher, publisher.prepare_publication(draft["article"], record, persist)


def reconcile(config, draft_id, queue, publisher_factory, *, after_verified=None, notify=None,
              slug_factory=None, verifier_factory=DeploymentVerifier):
    """One bounded check, no sleep loop. May retry a previously approved failed push.

    Returns (True, URL) only for verified/publication-complete; pending/failed is False.
    Does not approve an unapproved or edited draft. Safe for a coordinator/CLI retry.
    """
    draft = queue.get_draft(draft_id)
    if not draft:
        return False, "초안을 찾을 수 없습니다."
    if draft.get("status") == "published":
        return True, draft.get("published_url", "")
    if draft.get("status") not in ("approved", "pushed", "deployment_pending") or not approval_is_current(draft):
        return False, "이 리비전에 대한 저장된 사람의 승인이 없습니다."
    try:
        publisher, record = _prepare(config, draft, queue, publisher_factory, slug_factory)
        verification = verifier_factory(config, publisher.repo_root).check(record)
        if not queue.record_publication(draft["draft_id"], {"verification": verification}, "deployment_pending"):
            return False, "배포 검증 결과 저장 실패. 다시 확인하세요."
        if verification.get("status") != "verified":
            return False, "배포 확인 대기: " + verification.get("message", "확인되지 않았습니다.")
        if after_verified:
            after_verified(draft, record)
        if not queue.mark_published(draft["draft_id"], record["slug"], record["url"]):
            return False, "검증 완료 후 발행 상태 저장 실패. 다시 확인하세요."
        if notify:
            try:
                notify(draft, record)
            except Exception:
                # Live publication stays true even when a notification channel is unavailable.
                queue.record_publication(draft["draft_id"], {"notification_status": "failed"})
        return True, record["url"]
    except Exception as exc:
        return False, f"배포 확인 재시도 필요 ({type(exc).__name__}). 저장된 승인·커밋 기록은 유지됩니다."
