# The core-work reader: confirmed lines, quoted words, an order and never a rating

**Date:** 2026-10-28 · **Decided by:** the owner ("yes build the reader, test on Ferrari and Bonaventura", 2026-10-27;
"no the phrase like understand my counterpart's needs ... are very vague and we should not include such things"),
after the step-by-step measurement on Ferrari ([evals](../evals/2026-10-27-core-work-reader-ferrari.md)) · **Status:**
accepted, built ([component](../build/components/core-work-reader.md))

## Why
Titles and keywords cannot tell a role's work from a job that shares its words: on Ferrari's CRM role, CRM email
marketers and Salesforce people from IT matched as well as the people who roll a CRM platform out to dealers. The
measurement showed what decides it: the text read in order, quotes that describe work (never a title), and the
role's look-alikes named; and that a model's guesses at the look-alikes change from run to run, while a recruiter's
confirmation fixes them.

## Decisions
1. **The lines are the role's, confirmed by a person.** The desk proposes four to six work lines and two to four
   look-alikes (`WorkLineClaim`); nobody is read until a person confirms or types one. A re-read never replaces a
   person's line. A line is a fact about the role that rates nobody, so a change re-rates no one.
2. **Evidence is their own words about their work.** Every piece of a quote must be literally in their CV or profile,
   with one piece of at least four words outside any title, heading or skills list (code). A phrase about a quality,
   an attitude or a wish is never evidence (told to the model; owner, 2026-10-27).
3. **It orders, it never rates.** Within a band: the work shown first, nothing either way next, a look-alike as main
   work last. No number is shown or stored; the card says which lines their words show and quotes them. Some
   look-alike work among other work demotes nobody.
4. **The desk's model, not the reasoning one.** grok-4.7 cost nine times as much and was not better on the marks; the
   confirmed lines mattered more than the model.
5. **Kept like the deeper look:** in the task's result, erased with the person; what the model writes about them in
   its own words is never kept; quiet in the activity log, its prompt never logged.
6. **Who is read:** Priority and Review later, once the role has a confirmed line; again when the lines change or a CV
   arrives; never someone who said stop. About a fifth of a cent a person, inside the monthly model budget.

## Measured on the live roles
See below, written after the first readings on Ferrari's CRM role and Bonaventura's marketing role.
