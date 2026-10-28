# The search that learns from its own results: what was measured, what stays

**Date:** 2026-10-28 · **Decided by:** the owner ("build a test suite that includes your suggestions, then build a
search on three roles … compare … if it is better I will consider making those changes"; then "what and why should
we add/change … based on improvements and clear evidence findings only"; "yes do that") · **Status:** accepted, built

## Why
A review of the search loop (2026-10-28) found that it remembered what it had searched but learned nothing from what
it found: every company got the same titles in the same order whatever each title had produced, a company that gave
strong people was not searched deeper first, and the role's ideally-haves never shaped a search. The desk's own
records showed the cost: 97 of 207 searches ($2.94 of $6.06) had gone to titles that found nobody strong.

## What was measured
Six rules were proposed. Five were built behind a plan rule and measured; one (the owner's pass reasons shaping the
search) needs decisions nobody has made yet and was not measured.

1. **The live A/B.** Old loop against new, on two copies of the desk, from the same starting point (the role's search
   history reset, its company list kept), $1.20 of searches each, the career readings between batches as the desk does
   them. Strong people found (as rated now) and total spend, searches and readings:

   | Role | Old | New | Found by both |
   |---|---|---|---|
   | Procure AI | 10 for $1.92 (25 searches) | 11 for $2.01 (32) | 10 |
   | Bonaventura | 19 for $1.81 (46) | 18 for $2.05 (49) | 15 |
   | Ferrari | 14 for $1.56 (23) | 13 for $1.54 (36) | 12 |

   The same people, at the same quality (the core-work reader's groups matched). The new loop's extra person at
   Procure AI came from a productive company's second title; its losses at Bonaventura came from the smaller first
   search (Aeffe gave the old loop 7 strong from one 48-result search, the new 4 from 25).
2. **Title retirement, replayed exactly over the 207 recorded searches** in the order they ran: 51 searches skipped,
   $1.21 of $6.06 saved (20%), zero strong people lost (Ferrari 23 skipped, InSAR 24, Bonaventura 4, Procure AI 0).
   The A/B could not show this: at $1.20 no title reaches six barren searches.
3. **The second-angle search** (a search phrased from the role's confirmed work or its ideally-haves, at a company
   whose titles had found nobody strong): 18 real searches on Ferrari and Bonaventura, $0.70, 0 strong; 76 of 150
   results were people the title searches had already found. Those companies do not hold the people; other words do
   not change that.

The A/B spent $12.55 in all (Exa and xAI), recorded in the copies' ledgers.

## Decisions
1. **A title that finds nobody retires.** After six company searches with a title that found no strong person, the
   title is not searched again; the ad's own title never retires. Titles are tried in the order of what each has
   found (strong people per search). Proven on the desk's own history; it saves money, it finds nobody new.
2. **Deep where it gives.** A company whose searches found two or more strong people gets its next title before any
   other company's second, up to half a run; then every company never searched gets its first; one search per company
   per run, so each run's results shape the next. Its peer search comes at two strong people, not three. Neutral to
   slightly positive in the A/B, and free.
3. **Both are on by default** (`rules.adaptive`, 1), switchable off on a plan.
4. **Dropped, on the evidence:** the smaller first search (lost strong people at the richest companies); the
   second-angle search (found nobody). **Not taken, unmeasured:** the pass reasons in the search, fewer and deeper
   research rounds, a derived role profile replacing the hand lists.
5. **The qualities an ad lists are never requirements** (a reader fix found on the way): "Passion for innovation",
   "Commitment to … core values", "Strong results orientation and attention to detail", "Able to operate under
   pressure", "Excellent interpersonal and communication skills", "Strong hands-on and problem-solving approach" had
   become Ferrari's must-haves and flowed into the brief, the work lines and the call brief. The ad reader's trait
   filter now drops such lines; a named skill ("Salesforce knowledge") and a real ask ("Availability to travel
   extensively") stay. It applies to ads read from now on.

## Expected effect
The same people, about a fifth less search spend over a role's life, found a little sooner. Measured again on the
next real role's run.
