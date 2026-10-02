# Golden eval: GREEN

Run 2026-10-02T21:46:20 · model `grok-4.20-0309-non-reasoning` · 13 files (11 CVs) · cost $0.0822

PASS: 114 · FAIL: 0 · NOT CHECKED: 0 · NOT RUN: 13 · INFO: 3

Automated tests: `120 passed, 15 skipped in 38.92s`

| Case | Check | Result | Detail |
|---|---|---|---|
| bianca-photo | file | NOT RUN | Bianca Gogiltan CV (1).pdf is not in the folder |
| catalyst-jd | must.hiring_company_from_content | PASS | hiring company: 'CATALYST' |
| catalyst-jd | must.locations_mentioned | PASS | captured in requirements |
| catalyst-jd | must_not.candidate_identity_keys | PASS | none used as a match key |
| catalyst-jd | must_not.composite_score_emitted_against_software_cvs | PASS | 11 pairs, all a band with a reason |
| dmitry-ocr-email | file | NOT RUN | CV - Dmitry Chernyshov.pdf is not in the folder |
| jure-ocr-email | must.flags_on_some_contact | NOT RUN | premise absent: none of ['<email>', 'linkedin.com/in/jure-domainko'] is in this copy's text layer (it is clean), so there is nothing to flag |
| jure-ocr-email | must.identity_full_name_contains | PASS | names: 1 |
| jure-ocr-email | must_not.deterministic_match_keys | PASS | none used as a match key |
| nir-education-overlap | file | NOT RUN | Nir_Chodorov_CV_2026.pdf (1).pdf is not in the folder |
| procure-ai-jd-stale | must.flags | PASS | present |
| procure-ai-jd-stale | must.mobility_facts_when_extracted | INFO | residence / visa / relocation as three facts is Slice 1 |
| procure-ai-jd-stale | must_not.hiring_company | PASS | hiring company: 'Procure Ai' |
| procure-ai-jd-stale | must_not.auto_exclude_eu_candidates_outside_de_uk | PASS | no band set by place |
| triage-catalyst | distinctive tokens | INFO | oracle ['insar', 'd-insar', 'psi', 'interferometry'] · extracted ['insar'] |
| triage-catalyst | band for Veljko Djosovic CV (3).pdf | NOT RUN | person not in the folder |
| triage-catalyst | band for Bianca Gogiltan CV (1).pdf | NOT RUN | person not in the folder |
| triage-catalyst | band for Nir_Chodorov_CV_2026.pdf (1).pdf | NOT RUN | person not in the folder |
| triage-catalyst | band for Jure Domajnko - CV (1).pdf | PASS | do_not_submit  |
| triage-catalyst | band for CV - Dmitry Chernyshov.pdf | NOT RUN | person not in the folder |
| triage-catalyst | must_not.composite_score | PASS | 11 pairs, all a band with a reason |
| triage-procure-ai | distinctive tokens | INFO | oracle ['react', 'node', 'javascript', 'typescript'] · extracted ['node.js', 'react'] |
| triage-procure-ai | band for Jure Domajnko - CV (1).pdf | PASS | priority  |
| triage-procure-ai | band for Nir_Chodorov_CV_2026.pdf (1).pdf | NOT RUN | person not in the folder |
| triage-procure-ai | band for Bianca Gogiltan CV (1).pdf | NOT RUN | person not in the folder |
| triage-procure-ai | band for Veljko Djosovic CV (3).pdf | NOT RUN | person not in the folder |
| triage-procure-ai | band for CV - Dmitry Chernyshov.pdf | NOT RUN | person not in the folder |
| triage-procure-ai | must_not.composite_score | PASS | 11 pairs, all a band with a reason |
| triage-procure-ai | must_not.hiring_company | PASS | hiring company: 'Procure Ai' |
| veljko-concurrency-and-url | file | NOT RUN | Veljko Djosovic CV (3).pdf is not in the folder |
| cv-01 | processed | PASS | committed |
| cv-01 | nothing believed before a human acts | PASS |  |
| cv-01 | has a career history | PASS |  |
| cv-01 | has a name, or a note asking a human | PASS |  |
| cv-01 | every snippet is exactly at its location | PASS | mismatches: 0 |
| cv-01 | span failures at most 40% | PASS | 0 of 47 |
| cv-01 | no appearance or protected attributes | PASS |  |
| cv-01 | band, never a number, on job 1 | PASS | do_not_submit |
| cv-01 | band, never a number, on job 2 | PASS | do_not_submit |
| cv-02 | processed | PASS | committed |
| cv-02 | nothing believed before a human acts | PASS |  |
| cv-02 | has a career history | PASS |  |
| cv-02 | has a name, or a note asking a human | PASS |  |
| cv-02 | every snippet is exactly at its location | PASS | mismatches: 0 |
| cv-02 | span failures at most 40% | PASS | 0 of 34 |
| cv-02 | no appearance or protected attributes | PASS |  |
| cv-02 | band, never a number, on job 1 | PASS | priority |
| cv-02 | band, never a number, on job 2 | PASS | do_not_submit |
| cv-03 | processed | PASS | committed |
| cv-03 | nothing believed before a human acts | PASS |  |
| cv-03 | has a career history | PASS |  |
| cv-03 | has a name, or a note asking a human | PASS |  |
| cv-03 | every snippet is exactly at its location | PASS | mismatches: 0 |
| cv-03 | span failures at most 40% | PASS | 0 of 40 |
| cv-03 | no appearance or protected attributes | PASS |  |
| cv-03 | band, never a number, on job 1 | PASS | priority |
| cv-03 | band, never a number, on job 2 | PASS | do_not_submit |
| cv-04 | processed | PASS | committed |
| cv-04 | nothing believed before a human acts | PASS |  |
| cv-04 | has a career history | PASS |  |
| cv-04 | has a name, or a note asking a human | PASS |  |
| cv-04 | every snippet is exactly at its location | PASS | mismatches: 0 |
| cv-04 | span failures at most 40% | PASS | 4 of 37 |
| cv-04 | no appearance or protected attributes | PASS |  |
| cv-04 | band, never a number, on job 1 | PASS | do_not_submit |
| cv-04 | band, never a number, on job 2 | PASS | do_not_submit |
| cv-05 | processed | PASS | committed |
| cv-05 | nothing believed before a human acts | PASS |  |
| cv-05 | has a career history | PASS |  |
| cv-05 | has a name, or a note asking a human | PASS |  |
| cv-05 | every snippet is exactly at its location | PASS | mismatches: 0 |
| cv-05 | span failures at most 40% | PASS | 0 of 52 |
| cv-05 | no appearance or protected attributes | PASS |  |
| cv-05 | band, never a number, on job 1 | PASS | do_not_submit |
| cv-05 | band, never a number, on job 2 | PASS | priority |
| cv-06 | processed | PASS | committed |
| cv-06 | nothing believed before a human acts | PASS |  |
| cv-06 | has a career history | PASS |  |
| cv-06 | has a name, or a note asking a human | PASS |  |
| cv-06 | every snippet is exactly at its location | PASS | mismatches: 0 |
| cv-06 | span failures at most 40% | PASS | 0 of 51 |
| cv-06 | no appearance or protected attributes | PASS |  |
| cv-06 | band, never a number, on job 1 | PASS | priority |
| cv-06 | band, never a number, on job 2 | PASS | do_not_submit |
| cv-07 | processed | PASS | committed |
| cv-07 | nothing believed before a human acts | PASS |  |
| cv-07 | has a career history | PASS |  |
| cv-07 | has a name, or a note asking a human | PASS |  |
| cv-07 | every snippet is exactly at its location | PASS | mismatches: 0 |
| cv-07 | span failures at most 40% | PASS | 0 of 42 |
| cv-07 | no appearance or protected attributes | PASS |  |
| cv-07 | band, never a number, on job 1 | PASS | priority |
| cv-07 | band, never a number, on job 2 | PASS | do_not_submit |
| cv-08 | processed | PASS | committed |
| cv-08 | nothing believed before a human acts | PASS |  |
| cv-08 | has a career history | PASS |  |
| cv-08 | has a name, or a note asking a human | PASS |  |
| cv-08 | every snippet is exactly at its location | PASS | mismatches: 0 |
| cv-08 | span failures at most 40% | PASS | 2 of 14 |
| cv-08 | no appearance or protected attributes | PASS |  |
| cv-08 | band, never a number, on job 1 | PASS | priority |
| cv-08 | band, never a number, on job 2 | PASS | do_not_submit |
| cv-09 | processed | PASS | committed |
| cv-09 | nothing believed before a human acts | PASS |  |
| cv-09 | has a career history | PASS |  |
| cv-09 | has a name, or a note asking a human | PASS |  |
| cv-09 | every snippet is exactly at its location | PASS | mismatches: 0 |
| cv-09 | span failures at most 40% | PASS | 0 of 26 |
| cv-09 | no appearance or protected attributes | PASS |  |
| cv-09 | band, never a number, on job 1 | PASS | do_not_submit |
| cv-09 | band, never a number, on job 2 | PASS | do_not_submit |
| cv-10 | processed | PASS | committed |
| cv-10 | nothing believed before a human acts | PASS |  |
| cv-10 | has a career history | PASS |  |
| cv-10 | has a name, or a note asking a human | PASS |  |
| cv-10 | every snippet is exactly at its location | PASS | mismatches: 0 |
| cv-10 | span failures at most 40% | PASS | 0 of 30 |
| cv-10 | no appearance or protected attributes | PASS |  |
| cv-10 | band, never a number, on job 1 | PASS | priority |
| cv-10 | band, never a number, on job 2 | PASS | do_not_submit |
| cv-11 | processed | PASS | committed |
| cv-11 | nothing believed before a human acts | PASS |  |
| cv-11 | has a career history | PASS |  |
| cv-11 | has a name, or a note asking a human | PASS |  |
| cv-11 | every snippet is exactly at its location | PASS | mismatches: 0 |
| cv-11 | span failures at most 40% | PASS | 1 of 28 |
| cv-11 | no appearance or protected attributes | PASS |  |
| cv-11 | band, never a number, on job 1 | PASS | priority |
| cv-11 | band, never a number, on job 2 | PASS | do_not_submit |
| all | one person per CV (no merges) | PASS | 11 CVs |

GREEN needs zero FAIL and zero NOT CHECKED. NOT RUN means the person's file is not in the folder.
Only a human declares the Slice 0 gate green, in docs/decisions/.
