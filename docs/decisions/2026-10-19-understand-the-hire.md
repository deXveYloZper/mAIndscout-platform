# Understand the hire before searching, and measure every change first

**Date:** 2026-10-19 · **Decided by:** the owner ("agree. tread carefully, what we do not want is to have worse results
once this is implemented. Go"), after a check of the Marketing Manager role (Bonaventura) · **Status:** accepted; step A
built, steps B–F to come in order

## Why
The owner's review of the marketing role's strong list:
- "Tommaso Galli, Communication Manager at Prada Group, 12,213 staff": a 62-person brand will hardly move someone from a
  big house;
- "a senior would be okay, but a global head of influencer marketing is definitely a strong reach";
- "several CRMs and so many other titles that are not very close to the original job description title".

Tracing the 57 strong people through each step showed where it went wrong:
- **The search looked only inside five giant houses.** All 187 finds came from Prada, Dolce&Gabbana, Valentino,
  Safilo and Brioni. 52 of the 57 strong work at companies of 5,000+ people, nobody found works at a company under 50,
  and 5 at 51–500.
- **The career reading counted things that are not jobs.** Tommaso Galli's "small brand experience" was six months
  as a baker and six years at a 7-person website. A media director's came from a club's membership board, and a brand
  director's from teaching.
- **The rules missed:**
  - size: 51–1,000 was one band;
  - work: "experience at a small brand" counted any job, whatever the work;
  - level: there was no ceiling (15 heads and 7 directors were strong for a manager role);
  - kind of work: CRM, media and merchandising all counted as "marketing";
  - nothing compared where they work now with the client.

## The plan (owner, 2026-10-19), in order, each step checked before the next
- **A. Fixes that need no new reading, and the yardstick.** This step; details below.
- **B. A role brief.** Research the company in depth (its markets, where its people are, what it has done lately) and
  write a few lines on what this hire will really do. Each line is marked from the ad, from research, or "our reading".
  - The ad's sentences go into three groups. Those used to search and rate are confirmed once. Those for the
    conversation need no confirmation: they become the call checklist, and the answers become evidence of a person's
    strengths. The rest is context.
  - When "our reading" decides something and there is no brief or call transcript, ask the uploader 3–5 targeted
    questions.
  - The owner's example: a Japanese brand expanding into Europe needs someone hands-on, which by itself rules out
    regional heads at big houses.
- **C. Finer kind of work, level and a move check.**
  - Kind of work: specialisms through the existing step reader, with a longer fixed list. All-round marketing, CRM,
    media, merchandising and editorial are told apart.
  - Level: from the role brief and the person's companies, never from salary. The owner: "we really cant make a
    decision on salary, unless we do have reliable knowledge of payscales".
  - Move check: someone at a company two or more size bands bigger than the client is a reach. The exceptions are a
    step up for them, or recent time at a company the client's size. The owner: we need "a deeper understanding of a
    person's companies" for this.
- **D. The search.** Clear the marketing role's search: its suggestions leave the list but stay in the talent pool.
  Choose companies by size and situation next to the client's. Search big houses only for people one level below the
  role.
- **E. Less text on screen.** If a line does not change what you do next, it moves behind a click (it is not deleted).
  One verdict and one "why" line per card. A preview comes first.
- **F. Why they might move.** A short note on each strong person's call brief: public facts about their company and
  scope, against what the role offers. What may hold them back is written as questions, never personal life.

## Step A (built 2026-10-19)
1. **Company sizes in five bands** (`domain/profile.SIZE_BANDS`): 1–50, 51–250, 251–500, 501–5,000, 5,000+.
   - The owner: up to 50 is small, 51–250 and 251–500 are different, and "everything above 500 is already big". 250 is
     also the EU's line for a mid-size company.
   - An employer requirement may ask for a size in people (`min_staff`, `max_staff`; schema updated; typed on the
     hiring profile as "Company size").
   - A size alone counts companies like a client. Agencies, consultancies, public bodies and non-profits count only when
     the requirement names them; the start-up / scale-up reading never counted them either. A first what-if showed a PR
     agency and a fashion trade body turning two people strong.
   - The marketing role's "small or mid-size brand" became "up to 500 people". It was the kinds start-up and scale-up
     (51–1,000), a wording added in this build, not the owner's.
2. **A board seat, volunteering or mentoring is not a job.** It is read from the title when the profile is built, like
   the level (`profile.side_role`).
   - It was tested on every title on the desk. Ten board, volunteer and mentor roles are marked.
   - Lecturers, tutors, "Client Advisor" and "Brand ambassador" (real luxury retail jobs), advisors, and executive or
     management boards stay jobs.
3. **A kind of company or a size counts only years in the role's kind of work** (with the work that builds on it, as
   relevant years count it). What is not wanted still counts every job.
4. **"Not from" a company means its people now, and anyone who left it less than 6 months ago** (`recent_months` on
   the requirement, default 6). The owner: "usually there is no more than 2 year no-compete, so if people have previously
   worked and do not qualify in the 6-months it should be fine." It used to rule out anyone who had ever worked there.
5. **The yardstick: `python -m maindscout match-eval`.**
   - It re-matches everyone on the open roles with the code as it is, over today's facts, with a career profile built
     afresh, in a session that is rolled back. It is free.
   - It compares the result with the verdict the desk shows, with the owner's own decisions on the Sourcing tab (reach
     out means strong, not for this role means not strong), and with hand labels in `core/eval-reports/match-labels.json`
     (git-ignored: it names people).
   - With the code unchanged it must report no moves. That held on all three open roles before step A.

**What step A changed** (the what-if, then applied):
- **AI Product Engineer and the InSAR role:** no verdict changed. The owner's decisions on Procure AI still agree 21 of
  22 (Adrian Hupka, chosen by hand, reads possible).
- **Marketing Manager:** strong went from 57 to 61, possible from 69 to 73, and unlikely from 60 to 52.
  - Eight people who left Valentino long ago are no longer ruled out (seven strong, one possible).
  - Three dropped from strong to possible: one whose small-brand time was teaching, and two whose time was at companies
    of 501–1,000, which now count as big.
- **The seven hand labels** (Tommaso Galli, Piera Valentina Toniolo and five CRM specialists should not be strong) are
  still wrong. They are step C's to fix: the move check, the level, and the finer kind of work.

## Step B (built 2026-10-19, the owner's "go ahead with B")
1. **The notes reader drops no ask.** The owner's Bonaventura notes had said "not too senior like global and
   regional, not from big brands, ideally from small up to 200 people", and only the Milan, Valentino and salary asks
   were read.
   - Sizes in people are read in the desk's words ("big" is over 500).
   - A limit on seniority is its own "not wanted" requirement (head and above).
   - An ask no list can hold is kept for the conversation.
   - The notes were read again. "Up to 200 people" replaced the typed "up to 500", which had been a stand-in written in
     this build; match-eval showed three strong people move to possible, one hand label fixed, none made worse.
2. **The two limits rate nobody yet.** The seniority limit and "not from big brands" are read and shown; step C defines
   how they rate, through match-eval first.
3. **A role brief** ([role brief](../build/components/role-brief.md)): situation, core work, team, hands-on, market,
   reports to, level. Each line comes from the ad, the notes or research (quoted, checked) or is our reading, and a
   reading that changes whom to look for carries one question, at most five. One model call, about half a cent; the
   first two briefs cost $0.008.
   - Bonaventura: entering Italy and Europe, leads a small Milan team and agencies, steps into the work; level from the
     owner's notes; one question, who the role reports to and where.
   - Procure AI: every line said by the ad, so no questions.
4. **Three groups** for the requirements: what the desk searches and rates by, what is for the conversation (it becomes
   a call question, nothing to confirm), and context. The screens come with step E, preview first.

## Not changed
- The kinds start-up and scale-up keep their meaning (a stage; by size only when no funding is known).
- Industry years still count every real job.
- Salary is never a rule.
- No years-of-experience ceiling, which would work like an age filter: level and the role's scope are the levers.

Pages: [matching](../build/components/matching.md), [career profiles](../build/components/career-profiles.md),
[hiring profiles](../build/components/hiring-profiles.md), [match eval](../build/components/match-eval.md).
