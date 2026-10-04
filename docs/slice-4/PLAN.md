# Slice 4 — ATS core and import

**Status: UNLOCKED** 2026-10-04 (Slice 3 gate green). **Rescoped** 2026-10-04 by the owner: mAIndscout is the source of truth, not an accessory to an ATS ([decision](../decisions/2026-10-04-source-of-truth-and-imports.md)). Waiting for the owner to approve this plan.

---

## User-visible result

A desk can run on mAIndscout without another ATS: every person and client has a relationship history and a "last contacted / last verified" date, jobs move through a full pipeline to placement, clients' answers are recorded (a client rejection is a wall), and stale people and companies are flagged for refresh. A new desk brings in up to 100 candidates and 25 clients it knows, approving their facts as they arrive; anything more is paid analysis.

## In scope, in order

1. **Relationship memory.** Activity timeline per person and per company (calls, emails, notes, Brief answers, submissions); last contacted / last verified; notes; tags and talent pools; contacts at client companies (hiring managers).
2. **Full pipeline.** Stages new → contacted → screened → submitted → interviewing → offer → placed (and passed / withdrawn, with reasons); submissions to a client with the client's feedback; a client's rejection blocks the person for that client.
3. **Freshness.** A stale flag on every person and company (nothing verified for N months), and a weekly "re-contact these" list (most valuable stale people first).
4. **Import.** CSV first (one generic ATS export format), one ATS connector later. Free: 100 candidates and 25 clients per account, each reviewed and approved by the account holder as it arrives. Beyond that: a quote from the cost ledger at compute cost × 1.9, then the work is done as background tasks. Export of the desk's own data always free.
5. **Drafts.** Messages drafted from approved facts, the public job, the Brief and the thread only; the first send of each kind is done by a person; any reply stops follow-ups. (Mailbox choice to be made by the owner when we get here.)

## Out of scope

- Multi-user teams and permissions, inbound job posting / career pages, fees and invoicing (later slices)
- Research gateway, BD outbound to employers (Slice 5)

## Gate to unlock Slice 5

- [ ] A desk can run real jobs end to end on mAIndscout (relationship memory, pipeline to placed, client feedback)
- [ ] Client rejection is a wall (tested)
- [ ] Stale people and companies are flagged and listed for refresh
- [ ] Import: 100 / 25 free with approval; beyond that only as paid analysis; nothing unverified becomes a fact
- [ ] Any reply halts follow-up (tested)
