# mAIndscout is the source of truth; imports are small, vouched for, or paid

**Date:** 2026-10-04 · **Decided by:** the owner · **Status:** accepted

## Decision
1. **We are the system of record, not an accessory to an ATS.** No outside system's data is believed as truth. An ATS or CRM can be connected, but only as a way to bring people and clients *in*; job status, pipeline and facts live here. This replaces the Slice 4 idea of attaching to a client's ATS and letting it own job status.
2. **Free import: 100 candidates and 25 clients per account.** That is about what one person can reliably know and vouch for. The account holder reviews and approves the facts as they come in, so nothing degrades the knowledge base.
3. **Anything beyond that is paid analysis, at compute cost plus 90%.** Bringing in 10,000 stale contacts is a guess, not knowledge: we only take it on as work we do (reading, researching, verifying), charged at our measured compute cost with a 90% markup. Unverified bulk records are never treated as facts.
4. **Don't over-engineer it.** Use mAIndscout as a fresh start, or a solid start from your actual knowledge, or pay us to do the work.

## Why (owner)
Most ATS databases are stale: nobody knows when a candidate was last contacted, companies are out of date apart from what is live, and every refresh costs the user effort. A platform is only effective if its facts are current and backed by a real relationship. Importing everything would turn the knowledge base into guesses.

## Consequences
- Slice 4 becomes "ATS core and import" ([plan](../slice-4/PLAN.md)): the platform covers what a desk needs day to day so it can be used without another ATS.
- The cost ledger already measures compute per task; paid imports are priced from it (cost × 1.9).
- Imported records keep their source and "as of" date as evidence; only facts the account holder approves, or that we verify, count.
- Export of a desk's own data stays available (trust and data-protection law), whatever was imported.
