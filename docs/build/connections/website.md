# Connection: platform ↔ website

**Status:** planned (contracts not yet written)

The website ([github.com/deXveYloZper/mAIndscout](https://github.com/deXveYloZper/mAIndscout)) is the public face. It is one source of applications and clients, and it shows live roles and selected anonymised candidates to attract clients.

## Why
Recruiters work in the platform. The website should never hold its own copy of the truth, and must never see identifying data.

## Two directions

| Direction | What flows | Rule |
|---|---|---|
| Website → platform (ingest) | Contact/client inquiries; role applications with CVs | Applications become CVs on a job. Client inquiries become leads. |
| Platform → website (publish) | Live roles; anonymised showcase candidates | Only items a human marked "showcase". Anonymised here, before they leave. |

## Website seams to replace
In the website repo: `lib/inventory.ts` (static roles and people), `app/api/roles`, `app/api/people`, `app/api/contact`, and `data/inquiries.json`.

## To do
- Define both contracts in `slice0/api/openapi.yaml` (or a sibling file) before building either side.
- Decide the anonymisation fields and the showcase approval step.
