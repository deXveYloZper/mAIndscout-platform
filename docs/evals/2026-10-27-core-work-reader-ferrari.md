# The core-work reader, measured on Ferrari's CRM role (2026-10-27)

**Status:** an experiment, not built. Nothing about any person was written; the cost is in the ledger
(`core_work_lines`, `core_work_check`: $1.88 in all on the day).

**What it does.** A model writes a role's core work (four to six lines) and its "not this work" (jobs that share
its words but are different jobs) from the role's own material. It then reads each strong or possible person's own
words and quotes them for each line. It only orders people within their band, never changes a rating. Measured on
the 61 strong or possible people found for the CRM & Client Data Specialist role, and the CV of the person the
client chose to interview.

**Pass marks** (owner, 2026-10-27): the interviewee at the top of the strong; the person the recruiter was curious
about "but still light" lower; CRM email marketers below CRM operations and roll-out people. (Nobody outside the
years band is the matching rules' mark; the reader never changes a band.)

| Run | What changed | Interviewee's CV | Her public profile | "Still light" | Email/campaign people vs the rest (mean rank) | Cost |
|---|---|---|---|---|---|---|
| 1 | first version | #30 | 7th of 21 strong, on titles | #7 | 24 vs 38, fails | $0.10 |
| 2 | CVs read in column order ([decision](../decisions/2026-10-27-two-column-pdf-reading.md)); a title, heading, skills list or single word is never evidence | #1 | no evidence (titles only) | #21 | 26 vs 38, fails | $0.10 |
| 3 | and "not this work" lines, written by the model | #1 | no evidence | #50 | 39 vs 24, passes | $0.13 |
| 3b | and "a NOT line is never a smaller part of this work" | #4 | no evidence | #39 | 36 vs 27 | $0.13 |
| 4 | run 3 on grok-4.7, a reasoning model | #2 | no evidence | #61 | 32 vs 31, fails | $1.18 |
| 5 | grok-4.7's lines with one look-alike added, as a recruiter would confirm them; read by the desk's model | #1 | no evidence | #61 | 35 vs 28, passes | $0.13 |

**What it shows.**
- The text comes first: with her CV read in column order, the interviewee's CV went from #30 to #1, on her own
  sentence about training users worldwide on Salesforce.
- The "not this work" lines decide the order, and a model's guesses at them change from run to run. The reasoning
  model wrote fairer ones (configuring Salesforce from IT, selling at a dealer) but left out CRM email campaigns, the
  look-alike that matters most for this role. Told "never a smaller part of this work", the desk's model wrote only
  such lines. A recruiter's confirmation of the lines matters more than the model.
- The reasoning model costs about nine times as much ($0.019 a person, 19 seconds) and was not better on these marks.
- Public profiles mostly say little in their own words: 30 to 46 of the 61 gave the reader nothing to quote (most
  list titles and skills only), so it can only order the rest. The interviewee's public profile is titles only; the desk's title rules found her, not
  this reader.

**Next, the owner's call:** the core-work and not-this-work lines as part of the role brief, proposed by the model and
confirmed by the recruiter; the reader on CVs, call notes and the public profiles that describe work, ordering within
a band and showing its quotes; on the desk's model (about $0.002 a person).
