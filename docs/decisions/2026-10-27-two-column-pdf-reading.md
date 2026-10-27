# Two-column CVs: read in order, and the doubtful ones reported

**Date:** 2026-10-27 · **Decided by:** the owner ("yeah we need to have a proper fix, so go one by one"; "yes go ahead
with pdfminer.six"; then "lets not focus too much on this … if there is a problem or CV is probably unreadable or is
split, we should report for manual user reading, keep what you have but also have a fallback"), after the measurements
below · **Status:** accepted, built

## Why
The core-work reader failed its first measurement on Ferrari's CRM role (2026-10-27). One cause was the text itself:
many CVs set a narrow sidebar beside the main column, and pypdf reads such a page line by line across. The two
interleave. The interviewee's CV read "...la formazione sul funzionamento eLingue Italiano Francese...", her sentence
broken by the sidebar and by a consent line at the page turn, so no quote of her real work could match.

## What was measured
The same checks on 46 test PDFs and the interviewee's CV, against the desk's previous reading: no word lost, no word
split or glued, each dated line's date still beside its words, and her sentence over the page turn whole.

| Reading | Files losing words | Files with split or glued words | Dates kept with their words | Page turn |
|---|---|---|---|---|
| pdfminer.six (free, a library that reads layout) | 17 | 10 | 222 of 245 | broken |
| The desk's column reading (pypdf layout mode) | 0 | 0 | 245 of 245 | whole |

pdfminer.six glued words together on some files ("aligningwith", "andability"), garbled section headings on others
("Education", "Experience", "Skills" no longer readable as words) and cut words at ligatures ("applicaɵon"). Docling,
a heavier reader built on machine-learning models, was not measured: a large download, and the owner asked to stop
working on PDF reading once the column reading passed.

## Decisions
1. **Two columns are read column by column** with pypdf's layout mode deciding the order only. The ordinary reading
   stays the reference for the words. A page without a clear gap down it, or whose narrow side is mostly dates, is
   read exactly as before. Ten of the 47 files are now read in columns.
2. **No more reading rules for odd layouts: report them.** A page that looks split but has a line across its top or
   foot, or whose column reading would lose or add a single character, is read as before and flagged
   (`unsure_layout_pages`, under `needs_vision`), so a person reads the file. One page of the 47 is flagged.
3. **Only documents read in columns change.** Keeping a repeated long line once (a consent line at the page turn) is
   done only in a document read in columns, so 9 of the 46 test PDFs read differently, all two-column CVs, and no job
   ad. Their saved model answers for the tests were recorded again ($0.05).
4. **Stored documents keep their reading** until a forced re-read (`text_repair` 3); the re-read's own rule retires
   the machine's earlier proposals it does not find again.

## Not done
Three columns, columns under a full-width header (flagged for a person to read, not read in columns), and Word
files. Scans stay flagged and unread (a vision model is still locked).
