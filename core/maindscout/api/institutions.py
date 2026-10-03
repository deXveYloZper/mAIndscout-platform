"""Universities and colleges in the shared public tier, with their QS rank (I3). Researched once per institution,
refreshed yearly; cost recorded as shared research (no org) under the research budget."""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from maindscout.api import costs
from maindscout.db.models import Institution
from maindscout.intelligence import institutions as engine

REFRESH = {"identified": timedelta(days=365), "not_identified": timedelta(days=90), "failed": timedelta(days=7)}
_DROP = re.compile(r"\b(the|of|and|at|in)\b|[^\w\s]")


def normalize(raw: str) -> str:
    return " ".join(_DROP.sub(" ", raw.lower().replace("&", " and ")).split())


def find(session: Session, raw: str | None) -> Institution | None:
    if not raw or len(raw.strip()) < 3:
        return None
    return session.scalar(select(Institution).where(Institution.normalized == normalize(raw)))


def resolve(session: Session, raw: str) -> Institution:
    found = find(session, raw)
    if found is None:
        found = Institution(name=raw.strip()[:300], normalized=normalize(raw))
        session.add(found)
        session.flush()
    return found


def due(inst: Institution, now: datetime | None = None) -> bool:
    if inst.researched_at is None:
        return True
    now = now or datetime.now(timezone.utc)
    return now - inst.researched_at > REFRESH.get(inst.research_status or "failed", timedelta(days=7))


def research(session: Session, inst: Institution, client, task_id: uuid.UUID | None = None) -> dict[str, Any]:
    costs.ensure_budget(session, None)
    try:
        out = engine.research_rank(inst.name, client)
    except Exception:
        inst.research_status, inst.researched_at = "failed", datetime.now(timezone.utc)
        session.flush()
        raise
    costs.record(session, None, "research_institution", out.cost, task_id=task_id)
    inst.researched_at = datetime.now(timezone.utc)
    inst.research_status = "identified" if out.identified else "not_identified"
    if out.identified:
        inst.official_name, inst.country = out.official_name, out.country if out.country and len(out.country) == 2 else None
        if out.band:
            inst.rank, inst.rank_text, inst.rank_band = out.rank, out.rank_text, out.band
            inst.ranking = f"{engine.RANKING} {out.edition}".strip() if out.rank else engine.RANKING
            inst.source_url, inst.quote = out.source_url, out.quote
    session.flush()
    return {"identified": out.identified, "band": inst.rank_band, "rejected": out.rejected, "usd": out.cost.get("usd", 0)}


def rank_of(session: Session, raw: str | None) -> dict[str, Any]:
    inst = find(session, raw)
    if inst is None or not inst.rank_band:
        return {}
    return {"rank": inst.rank, "rank_band": inst.rank_band, "rank_source": inst.ranking}
