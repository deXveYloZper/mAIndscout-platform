# Every kind of role, not only engineering

**Date:** 2026-10-18 · **Decided by:** the owner ("it is given a marketing role or a sales role, similar rules should apply
to ensure strong match results, not just building this for engineering"; "yes, add that" for reading a person's own job
descriptions); the mechanisms below were chosen in the build · **Status:** accepted, built

## Why
A check of the Marketing Manager role (Buona Ventura) showed the ad reader and matching had been tuned on engineering
ads:
- Only technologies got a skill word. "Influencer marketing", "CRM", "PR" and "events" had none, so no profile or CV
  could ever show them, and every row was "ask".
- "Demonstrated ability across several of the following areas: …" became eight separate must-haves.
- "Strongly preferred" came back as nice to have.
- "Calm, constructive and decisive" became a must-have, though personality is never a criterion.
- A profile's languages were never read, and a language it did not list counted as a must-have gap. Two such gaps make
  a match unlikely, so every Milan marketing manager whose profile lists no languages would have been unlikely.

## Decisions (all in code after the ad reader; its prompt and recordings are unchanged)
1. **A skill written as a short name is something a profile can show**, in any field. A name of up to four words,
   with no sentence and no quality word ("experience", "strong", "ability"…), becomes its own skill word. Skills typed
   on a hiring profile get the same.
2. **A list introduced as "several of", "any of" or "one or more of" is one requirement, met by any item,** even
   when it ends with "and".
3. **"Strongly preferred", "highly desirable", "a big plus" make a strong plus.**
4. **Personality is dropped in the ad reader too:** the hiring reader's words, plus a short list of traits ("calm",
   "decisive", "driven"…), for qualities only, never for skills ("data-driven marketing" stays).
5. **A found profile's languages are read**, in the profile's own language too ("Italiano", "Englisch"). So is what
   the person wrote under their own jobs ("- Created a node-based UI using react"). Exa's blurb about each employer
   is still never read.
6. **A language a profile or CV does not list is "ask", never a gap.**
7. **Stored profiles are read again for free** whenever a role's requirements change, for that role's current skill
   words (`discovery.reread_for_job`, before every re-match of the role).
8. **A title sets someone's level only when it is their job now or they held it at least a year.**
9. **Years asked for a kind of work are years of that work** (from the career profile), not of a whole career.
   (8 and 9 came from the first real marketing search: a Junior Marketing Specialist read as a strong match, as a
   "manager" with "8.2 years", from six months with a manager title and years spent translating and in retail.)

## Not changed
A role with no core skill (most marketing and sales roles) still starts everyone as possible. Strong comes from the
full match over a career profile (kind of work, level, years, industry, background, the role's skills and languages),
which every person found by sourcing gets.

Pages: [web discovery](../build/components/web-discovery.md), [hiring profiles](../build/components/hiring-profiles.md),
[matching](../build/components/matching.md), [gap table](../build/components/gap-table.md).
