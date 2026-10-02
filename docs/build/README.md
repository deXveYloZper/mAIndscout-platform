# Build documentation

What has actually been built, why, how, and how the parts connect. Short on purpose.

This is separate from the **spec** (`00`–`05`, `docs/VISION.md`, `docs/ROADMAP.md`), which says what we *intend* to build. If the two differ, this folder describes reality and the spec describes the target.

## Start here

| I want to know… | Read |
|---|---|
| What exists right now, and its status | [STATUS.md](STATUS.md) |
| How the pieces fit and depend on each other | [ARCHITECTURE.md](ARCHITECTURE.md) |
| What one component is, why it exists, how it works | [components/](components/) (one page each) |
| How two systems talk (platform ↔ website, API ↔ cockpit) | [connections/](connections/) |
| Why a decision was made | [../decisions/](../decisions/) |
| What changed and when | [LOG.md](LOG.md) |
| Golden eval results | [../evals/](../evals/) |

## Rules (part of "done")

A change is not finished until its docs are. In the same commit:

1. **New component** → add `components/<name>.md` from [components/_TEMPLATE.md](components/_TEMPLATE.md), add it to [ARCHITECTURE.md](ARCHITECTURE.md) and [STATUS.md](STATUS.md).
2. **Changed behaviour or dependency** → update that component's page and every page it links to in *Depends on* / *Used by*.
3. **New connection or contract change** → add or update a page in `connections/`.
4. **Non-obvious choice** → add an ADR in `docs/decisions/` and link it from the component.
5. **Every merge to `development`** → one line in [LOG.md](LOG.md).

Keep each page under about one screen. If it needs more, split it. Link to code with relative paths rather than copying code into docs.
