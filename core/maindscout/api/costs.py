"""The cost ledger: every paid call is recorded, and a monthly budget stops paid work before it overspends."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, literal_column, select
from sqlalchemy.orm import Session

from maindscout.db.models import CostEntry
from maindscout.settings import env

DEFAULT_MONTHLY_BUDGET_USD = 25.0


class BudgetExceeded(RuntimeError):
    permanent = True  # retrying will not help until the budget is raised or the month turns

    def __init__(self, spent: float, budget: float):
        super().__init__(f"Monthly budget reached: ${spent:.2f} of ${budget:.2f}. Raise MONTHLY_BUDGET_USD to continue.")


DEFAULT_RESEARCH_BUDGET_USD = 10.0


def monthly_budget(shared: bool = False) -> float:
    """The desk's budget, or (shared=True) the budget for shared company research."""
    name, default = ("RESEARCH_MONTHLY_BUDGET_USD", DEFAULT_RESEARCH_BUDGET_USD) if shared else ("MONTHLY_BUDGET_USD", DEFAULT_MONTHLY_BUDGET_USD)
    try:
        return float(env(name, str(default)))
    except ValueError:
        return default


def _month_start() -> datetime:
    now = datetime.now(timezone.utc)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def month_spent(session: Session, org_id: uuid.UUID | None) -> float:
    q = select(func.coalesce(func.sum(CostEntry.usd), 0)).where(CostEntry.created_at >= _month_start())
    q = q.where(CostEntry.org_id == org_id) if org_id else q.where(CostEntry.org_id.is_(None))
    return float(session.scalar(q) or 0)


def ensure_budget(session: Session, org_id: uuid.UUID | None) -> None:
    """Call before any paid work. Raises BudgetExceeded when this month's spend has reached the budget."""
    spent, budget = month_spent(session, org_id), monthly_budget(shared=org_id is None)
    if spent >= budget:
        raise BudgetExceeded(spent, budget)


def record(session: Session, org_id: uuid.UUID | None, purpose: str, cost: dict[str, Any], *,
           subject_type: str | None = None, subject_id: uuid.UUID | None = None, task_id: uuid.UUID | None = None) -> CostEntry:
    entry = CostEntry(org_id=org_id, purpose=purpose, model=cost.get("model") or "unknown",
                      input_tokens=int(cost.get("input_tokens") or 0), output_tokens=int(cost.get("output_tokens") or 0),
                      sources=int(cost.get("sources") or 0), usd=float(cost.get("usd") or 0),
                      subject_type=subject_type, subject_id=subject_id, task_id=task_id)
    session.add(entry)
    session.flush()
    return entry


def summary(session: Session, org_id: uuid.UUID) -> dict[str, Any]:
    start = _month_start()
    rows = session.execute(select(CostEntry.purpose, func.count(), func.sum(CostEntry.usd), func.sum(CostEntry.input_tokens),
                                  func.sum(CostEntry.output_tokens), func.sum(CostEntry.sources))
                           .where(CostEntry.org_id == org_id, CostEntry.created_at >= start).group_by(CostEntry.purpose)).all()
    day = func.date_trunc(literal_column("'day'"), CostEntry.created_at)  # a literal: Postgres must see one grouping expression
    days = session.execute(select(day, func.sum(CostEntry.usd))
                           .where(CostEntry.org_id == org_id, CostEntry.created_at >= start)
                           .group_by(day).order_by(day)).all()
    spent = month_spent(session, org_id)
    return {
        "month": start.strftime("%Y-%m"), "spent_usd": round(spent, 4), "budget_usd": monthly_budget(),
        "shared_research_usd": round(month_spent(session, None), 4), "research_budget_usd": monthly_budget(shared=True),
        "by_purpose": [{"purpose": p, "calls": n, "usd": round(float(u or 0), 4), "input_tokens": int(i or 0),
                        "output_tokens": int(o or 0), "sources": int(src or 0)} for p, n, u, i, o, src in rows],
        "by_day": [{"day": d.date().isoformat(), "usd": round(float(u or 0), 4)} for d, u in days],
    }
