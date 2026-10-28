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

## Measured on the live roles (2026-10-28: 152 readings, $0.36)
The lines were confirmed by the owner ("make your suggested changes and confirm both"): Ferrari's as the desk read
them, less one look-alike (reports and dashboards in Salesforce: reporting is part of a CRM data specialist's work);
Bonaventura's as read, plus one look-alike from the owner's own labels ("CRM specialist, not the ad's all-round
marketing job").

- **Ferrari (61 read):** 15 show some of the work, 41 nothing either way, 5 a look-alike as their main work. The person
  the recruiter found "potential but light" is last but one of the possibles (main work: configuring Salesforce); the
  strong match whose main work is CRM campaigns is last of the strong; the people with campaign work end the possibles;
  the roll-out and operations people lead both bands. The client's interviewee: her public profile lists titles only,
  so it shows nothing either way and she keeps her place mid-band; her CV, read in the measurement, came first. A
  public profile of titles cannot show the work; the title rules that found her stay the desk's way to find her.
- **Bonaventura (91 read):** 31 show the work, 37 nothing either way, 23 a look-alike as their main work (digital or
  performance only, global brand strategy at headquarters, CRM as a specialist). The three CRM specialists the owner
  labelled sit below every possible whose words show the all-round work (42nd, 43rd and 49th of 71), though not as
  look-alikes: their profiles list titles only. The person labelled for too hard a move stays possible (matching's
  rule) and is high within it, on the work his words show: the reader orders within a band, it never overrides one.
- **Both:** every quote is literally the person's words, no band or rating changed, and the Sourcing tab orders and
  shows them (its own share of the page's time: 0.05 seconds for 1,684 people).
