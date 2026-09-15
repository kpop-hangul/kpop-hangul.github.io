"""Bind an interactive approval to one exact article revision, then consume it."""
from copy import deepcopy
from hashlib import sha256
import json
from secrets import token_hex


def _fingerprint(session, field):
    payload = {"article": session.get(field), "slug": session.get("slug") if field == "data" else None}
    return sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


def invalidate_approvals(session):
    session.pop("draft_approval", None)
    session.pop("data_approval", None)


def issue_approval(session, field):
    token = token_hex(8)
    session[field + "_approval"] = {"token": token, "fingerprint": _fingerprint(session, field)}
    return token


def consume_approval(session, field, token):
    if not session or session.get("busy"):
        return None
    record = session.get(field + "_approval", {})
    if not token or record.get("token") != token or record.get("fingerprint") != _fingerprint(session, field):
        return None
    session.pop(field + "_approval", None)
    session["busy"] = True
    session["publication_inflight"] = True
    return {"article": deepcopy(session[field]), "slug": session.get("slug"), "session": session}
