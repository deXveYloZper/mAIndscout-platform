# Model recordings (free test runs)

**Status:** built 2026-10-05
**Code:** `core/maindscout/intelligence/recording.py`; used by `api/app.get_llm`, `api/task_handlers` (chat and web search), the golden eval and `tests/test_live_artifacts.py`; `cockpit/playwright.config.ts`.

## What
Every model answer can be recorded once and replayed as often as needed, at no cost. One setting, `LLM_REPLAY`:

| Mode | What happens |
|---|---|
| `off` (default) | The real model, nothing recorded. The desk itself always runs like this. |
| `auto` | Replayed when recorded; otherwise the real model is called and its answer saved. |
| `replay` | Recordings only. A request never recorded fails loudly ("No recorded answer for this jd_extraction request… record it once with LLM_REPLAY=auto"), and nothing is spent. |
| `record` | The real model for everything, refreshing the recordings. |

The e2e scripts pick the mode:
- `npm run e2e` runs in `auto`;
- `npm run e2e:free` runs in `replay`;
- `npm run e2e:record` runs in `record`.

The golden eval and the live test (`RUN_LIVE=1`) honour `LLM_REPLAY` too.

## Why
Model credits ran out on 2026-10-05, and every e2e run spent a few cents. Recording once makes the suite and the eval free to repeat. Replaying the same answers also makes them a fixed baseline: a change to the span check, matching or the cockpit is tested against identical model output.

## How
- **The key is the exact request:** instructions, input text, model, schema and call name (SHA-256). A changed prompt, a changed document or a different model is a new request, never answered with an old reply. No prompt contains today's date or a database id, so recordings stay valid across fresh test databases.
- **Stored** as one JSON file per answer in `LLM_RECORDINGS` (default `core/.llm-recordings/{chat|search}/{call}/`), written atomically.
- **Replayed answers carry the recorded tokens and cost,** so the cost ledger and Costs page look as they did when recorded. Nothing is actually charged.
- In `replay`, the real client is never even created, so no API key is needed. A missing recording is a permanent task failure (no retries).

## Privacy
Recordings contain what the model was sent and said, which includes real CV text. They are git-ignored (`core/.llm-recordings/`) and never leave the machine, like the eval reports. Erasing a person on the desk does not touch recordings made from test files. Delete the folder to remove them all.

## Tests
`core/tests/test_recording.py` (6):
- auto records once, then answers for free with the recorded cost;
- replay never builds the real client and fails loudly on a new request;
- a changed prompt, schema or model is a new key;
- web search is recorded too;
- record always calls;
- off is the real client, and a bad mode is refused.

Checked end to end: `npm run e2e:free` with no recordings stops at the first model call with the message above, and spends nothing.

## Known limits
- Recording needs model credits once. Until then, `e2e:free` runs only the steps that need no model (sign-in and the empty desk).
- An answer recorded before a prompt change is simply unused: stale files accumulate until the folder is cleared.
