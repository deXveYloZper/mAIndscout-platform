# The role's own titles, its countries and one former colleague; three bugs from the first hard-tech test

**Date:** 2026-10-30 · **Decided by:** the owner ("do a proper test of our platform ... i want to see what we found";
then "we cannot hard code every job family there is ... why our platform doesn't generate this itself, when it
understands the company and the role?"; then "yes build it, then measure again") · **Status:** accepted, built

## The test
Three hard-tech ads (Cambridge Aerospace, Senior GNC Engineer - Navigation; Destinus, Senior Propulsion Engineer (SRM);
ICEYE, Staff Electronics Engineer - Avionics) taken through the desk in the browser as a recruiter would: upload, brief,
work lines, requirements, countries, strategy, Search now, reading the activity log at each step. $14.49 in all
($5.47 of it competitor research).

Fixed during the test (each with a test): an ad whose emoji bullets read as NUL crashed job creation
([ingestion](../build/components/ingestion.md)); three company lists built at once deadlocked, two failed, so long
sourcing work now takes turns and a deadlock gets one more try ([tasks and costs](../build/components/tasks-and-costs.md));
a talent map listed known luxury pools for a rocket-motor role with "Not applicable" as their why and took their 227
companies, so such pools are dropped ([sourcing strategy](../build/components/sourcing-strategy.md)).

Found, not fixed (for the owner): the strong rule lets "ask" satisfy every must-have, so 70 strong people on the three
roles held about four real fits, and false strong people met the target and stopped each search after one or two
batches; Exa's "title at company" returns a company's staff rather than the title (at one company 47 of 50 results
worked elsewhere); searches are ordered by closeness to the client's business, not to the hire's work; the "far bigger"
rule leaves out the primes that feed defence start-ups; later roles' talent maps copy earlier roles' pools.

## Why titles of its own
The desk has 24 fixed job families written for its first roles (software, data, GIS, marketing, CRM) and one
hard-coded specialism (CRM). None fits GNC, avionics, propulsion or mechanical work, the fields the website sells. All
three roles were read as "engineering management" or "embedded / hardware"; their searches became "embedded software
engineer", "firmware engineer" and, at small companies, "embedded hardware at Spaceflux". A fixed list cannot grow
with 50 clients; each role's own reading can.

## Decisions
1. **The role reads its own titles** with its work lines (one call, about a fifth of a cent): the titles people doing
   this work carry, without seniority words and in the languages of the role's countries; the titles of its look-alike
   jobs; the work in a word. With the client's own people's titles once the strategy has found them. Proposed, and
   confirmed by a person with the lines. Kept as `WorkLineClaim` kinds `title`, `not_title`, `word` (schema extended,
   with a `rank` for the reading's order).
2. **Confirmed titles replace the family table's in the searches**, in their order, the ad's own title after them; a
   small company is searched for the role's word; a rebuild no longer brings back a family default a person removed.
   Nothing changes for a role until its titles are confirmed.
3. **A search looks in the role's countries**: the company's home country only when the role takes people there,
   else the role's country where most of its people are, else the role's first.
4. **One former colleague** of the client's people makes a company a target (`feeder_one`), ranked with the
   researched competitors, never ahead of them.
5. **No rating changes.** The measured rule below needs the owner's word first.

## Measured (2026-10-30, the live desk, read only except the titles proposed)
Titles read for all seven open roles ($0.018), e.g. Cambridge: GNC Engineer, Navigation Engineer, INS Engineer,
Inertial Navigation Engineer, GNC Ingenieur (look-alikes: guidance, control, flight dynamics engineers); ICEYE:
Electronics Engineer, Avionics Engineer, Electronics Design Engineer, Elektroniikkainsinööri (look-alikes: embedded
software, FPGA, RF engineers). Weak where a person's confirmation matters: Destinus's first title is the broad
"Propulsion Engineer" and no marine-propulsion look-alike; Ferrari's lack the luxury client-engagement titles;
Bonaventura's lack plain "Brand Manager".

**"Strong" if the person's own words show a central work line (V2), or also if a title held now or within three years
names the role's work (V4)**, on the roles with confirmed lines, against the owner's 6 labels and Claude's 70 labels of
the three test roles' strong people (from their careers, before the readings were seen):

| | owner labels | Claude's labels | strong: Bonaventura, Ferrari, Cambridge, Destinus, ICEYE |
|---|---|---|---|
| today | 6/6 | 8/70 | 20, 21, 27, 27, 16 |
| V2 words only | 5/6 (the Ferrari interviewee drops: titles only) | 61/70 | 10, 6, 5, 4, 1 |
| V4 words or title | 6/6 | 62/70 | 15, 17, 5, 5, 3 |

V4 keeps all three real fits and removes 54 of the 63 wrong strong people. What it still gets wrong is the titles, not
the rule: "Propulsion Engineer" keeps three naval-propulsion engineers; Ferrari's four client-engagement specialists
(CRM work by the owner's own CRM rule) and two Bonaventura brand managers drop until those titles are confirmed. One of
Claude's labels was corrected: a "satellite systems engineer" had been a GNC and AOCS engineer until 2024, which the
title test found and the labelling had missed.

**The next search batch** of each test role, planned with the titles as if confirmed (rolled back, nothing run):
Cambridge "embedded hardware at Tytan Technologies" became "GNC Navigation at Tytan Technologies", "Senior GNC Engineer
at Helsing" became "GNC Engineer at Helsing"; ICEYE "Staff Electronics Engineer at GomSpace" became "Electronics
Engineer at GomSpace" and its small companies "Avionics Electronics at …"; Destinus "embedded hardware at …" became
"rocket motor development at …". The countries rule moves MBDA from France to the UK, RUAG from Switzerland to
Germany, DigitalGlobe from the US to the UK. ICEYE gains 15 one-colleague former employers (Bittium, Etteplan, Silicon
Labs, Creotech among them, and some noise), none in its next batch.

## Next
The owner confirms or corrects each role's titles; then V4 is measured once more with the confirmed titles before the
owner decides on the strong rule.
