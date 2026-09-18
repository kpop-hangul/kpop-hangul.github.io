"""Bounded content checks, not factual verification or an AdSense prediction."""
import re
import hashlib
import json
from datetime import date, datetime


class ContentValidationError(ValueError):
    pass


def validate_metadata(article):
    """Validate the supported Astro metadata before it is serialized to YAML."""
    for key in ("author", "readingTime", "heroImage"):
        if key in article and not isinstance(article[key], str):
            raise ContentValidationError(f"{key}는 문자열이어야 합니다.")
    for key in ("featured", "draft"):
        if key in article and type(article[key]) is not bool:
            raise ContentValidationError(f"{key}는 true/false여야 합니다.")
    for key in ("pubDate", "updatedDate"):
        if key not in article:
            continue  # Publisher supplies a date when a generated draft has none.
        value = article[key]
        if isinstance(value, (date, datetime)):
            continue
        try:
            if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}(?:T.+)?", value):
                raise ValueError()
            datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            raise ContentValidationError(f"{key}는 유효한 ISO 날짜여야 합니다 (예: 2026-09-12).") from None
    if "songTitle" in article:
        for key in ("songTitle", "artist", "genre"):
            if not isinstance(article.get(key), str) or not article[key].strip():
                raise ContentValidationError(f"{key} must be a nonempty string")
        if article.get("difficulty") not in ("Beginner", "Intermediate", "Advanced"):
            raise ContentValidationError("Invalid lesson difficulty")
        if "chartRank" in article and (type(article["chartRank"]) is not int or article["chartRank"] < 1):
            raise ContentValidationError("chartRank must be a positive integer")
    if "summaryCards" in article:
        cards = article["summaryCards"]
        if not isinstance(cards, list):
            raise ContentValidationError("summaryCards는 배열이어야 합니다.")
        for card in cards:
            if not isinstance(card, dict) or any(not isinstance(card.get(key), str) for key in ("badge", "title", "desc")):
                raise ContentValidationError("summaryCards 각 항목에 badge/title/desc 문자열이 필요합니다.")
            if "icon" in card and not isinstance(card["icon"], str):
                raise ContentValidationError("summaryCards icon은 문자열이어야 합니다.")


def _operations_digest(value):
    # Keep the coordinator's blogops.content.digest serialization contract exactly.
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


def validate_operations_gate(article):
    """Verify the stored review still applies to this article, not a fresh fact audit.

    Legacy articles have no operations metadata. A present but malformed/stale gate
    cannot silently downgrade an orchestrated article into that legacy path.
    """
    if "operations" not in article:
        return
    operations = article["operations"]
    if not isinstance(operations, dict) or not isinstance(operations.get("workflow_id"), str) or not operations["workflow_id"].strip():
        raise ContentValidationError("operations 워크플로 식별자가 없거나 유효하지 않습니다.")
    gate, review = operations.get("gate"), operations.get("review")
    if not isinstance(gate, dict) or gate.get("status") != "passed" or not isinstance(review, dict):
        raise ContentValidationError("통과한 근거 검토 gate와 review가 필요합니다.")
    if any(not isinstance(gate.get(key), str) or not re.fullmatch(r"[0-9a-f]{64}", gate[key]) for key in ("article_hash", "review_hash")):
        raise ContentValidationError("검토 gate의 article_hash/review_hash가 유효하지 않습니다.")
    article_revision = {key: value for key, value in article.items() if key != "operations"}
    if gate["article_hash"] != _operations_digest(article_revision):
        raise ContentValidationError("근거 검토 후 글의 본문·메타데이터·이미지가 변경되었습니다. 팀 검토를 다시 실행하세요.")
    if gate["review_hash"] != _operations_digest(review):
        raise ContentValidationError("근거 검토 보고서가 gate에 기록된 버전과 다릅니다.")
    try:
        checked_at = gate["checked_at"]
        if not isinstance(checked_at, str) or datetime.fromisoformat(checked_at.replace("Z", "+00:00")).tzinfo is None:
            raise ValueError()
    except (KeyError, ValueError, TypeError):
        raise ContentValidationError("검토 gate에 시간대가 포함된 checked_at이 필요합니다.") from None
    evidence_ids = gate.get("evidence_ids")
    if (not isinstance(evidence_ids, list) or not evidence_ids
            or any(not isinstance(item, str) or not item.strip() for item in evidence_ids)
            or len(set(evidence_ids)) != len(evidence_ids)):
        raise ContentValidationError("검토 gate의 근거 ID 목록이 없거나 유효하지 않습니다.")
    if (review.get("decision") != "pass" or review.get("rights") != "clear" or review.get("issues")
            or not isinstance(review.get("original_value"), str) or not review["original_value"].strip()
            or review.get("coverage_checked") is not True or review.get("requires_expert_review") is not False):
        raise ContentValidationError("독립 검토의 통과·권리·근거 범위·전문 검토 조건이 충족되지 않았습니다.")
    if "image_manifest" in gate:
        manifest = gate["image_manifest"]
        if not isinstance(manifest, list):
            raise ContentValidationError("검토 gate의 image_manifest는 배열이어야 합니다.")
        seen = set()
        for item in manifest:
            if (not isinstance(item, dict) or not isinstance(item.get("url"), str)
                    or not item["url"].startswith("/images/") or item["url"] in seen
                    or not isinstance(item.get("sha256"), str) or not re.fullmatch(r"[0-9a-f]{64}", item["sha256"])):
                raise ContentValidationError("검토 gate 이미지 경로·SHA256이 없거나 중복되었습니다.")
            seen.add(item["url"])
    claims = review.get("claims")
    if not isinstance(claims, list) or not claims:
        raise ContentValidationError("근거와 연결된 검토 주장 목록이 필요합니다.")
    text = article.get("title", "") + "\n" + article.get("description", "") + "\n" + article.get("markdown_content", "")
    for claim in claims:
        if not isinstance(claim, dict):
            raise ContentValidationError("검토 주장은 객체여야 합니다.")
        source, statement, quote = claim.get("source_id"), claim.get("claim"), claim.get("quote")
        if not isinstance(source, str) or source not in evidence_ids:
            raise ContentValidationError("검토 주장의 출처가 gate 근거 목록에 없습니다.")
        if (claim.get("assessment") != "supported" or not isinstance(statement, str) or len(statement.strip()) < 8
                or statement not in text or not isinstance(quote, str) or len(quote.strip()) < 12):
            raise ContentValidationError("검토 주장·근거 인용이 불완전하거나 현재 본문과 다릅니다.")


def validate_article(article, topic=None):
    if not isinstance(article, dict):
        raise ContentValidationError("글 응답은 JSON 객체여야 합니다.")
    validate_metadata(article)
    for key in ("title", "description", "category", "markdown_content"):
        if not isinstance(article.get(key), str) or not article[key].strip():
            raise ContentValidationError(f"필수 문자열 누락: {key}")
    if not isinstance(article.get("tags", []), list) or not all(isinstance(v, str) for v in article.get("tags", [])):
        raise ContentValidationError("tags는 문자열 배열이어야 합니다.")
    faqs = article.get("faqs", [])
    if not isinstance(faqs, list) or any(not isinstance(f, dict) or not all(isinstance(f.get(k), str) and f[k].strip() for k in ("question", "answer")) for f in faqs):
        raise ContentValidationError("FAQ는 비어 있지 않은 question/answer 객체 배열이어야 합니다.")
    validate_operations_gate(article)
    if article["markdown_content"].lstrip().startswith("---"):
        raise ContentValidationError("본문 안에 frontmatter를 넣을 수 없습니다.")
    if article.get("generation_status") == "failed":
        raise ContentValidationError("생성 실패한 글은 발행할 수 없습니다.")

    # Regression signatures of the three actual templates removed in this repair.
    body = article["markdown_content"]
    signatures = (
        ("체계적인 자동화 워크플로우", "주당 최소 5~10시간", "나만의 템플릿 자산화"),
        ("체계적인 실전 적용 프레임워크", "100% 무결점 처리", "수익률을 지속적으로 고도화"),
        ("2026년 예상 선정기준액", "약 213만 원 이하", "약 33만 4천 원"),
    )
    if any(sum(s in body for s in group) >= 2 for group in signatures):
        raise ContentValidationError("확인된 반복/오정보 템플릿입니다. 주제별로 다시 작성하세요.")
    for faq in faqs:
        answer = faq["answer"]
        if ("애드센스" in faq["question"] or "애드센스" in answer) and re.search(r"(완벽히?\s*(부합|반영)|승인\s*(보장|100%)|1,?500자.*(충분|반영))", answer):
            raise ContentValidationError("FAQ의 애드센스 승인 공식/보장 문구를 수정하세요.")
    if re.search(r"(승인|치료|수익).{0,12}100\s*%|100\s*%.{0,12}(승인|완치|보장)", article["title"]):
        raise ContentValidationError("제목의 승인/치료/수익 보장 표현을 수정하세요.")
    return article


def body_fingerprint(content):
    # Editorial illustrations are separate assets, not a new article body.
    # Keep duplicate detection stable when the same text gains an illustration.
    content = re.sub(
        r"<!-- article-illustration:([^\s]+) -->[\s\S]*?<!-- /article-illustration:\1 -->",
        "", content,
    )
    # Ignore headings/formatting: changing only a title must not create a new article.
    lines = [line for line in content.splitlines() if not line.lstrip().startswith("#")]
    return re.sub(r"[^a-z0-9가-힣]", "", " ".join(lines).lower())
