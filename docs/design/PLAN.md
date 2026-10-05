# Desk design: a modern, professional cockpit in the website's voice

**Status: DRAFT**, waiting for the owner's approval. No model calls needed.

## What's wrong today (from screenshots of every main page, 2026-10-06)
The desk shares the website's colours but none of its craft:
- **Navigation:**
  - nine equal text links in a row with nothing to say where you are or what's waiting;
  - on a phone they wrap into three rows;
  - there's no way to jump to a person or job by name from anywhere.
- **Everything is underlined monospace at one size.** Names, numbers, labels and links look alike, so nothing guides the eye. Monospace is right for the website's few big words but tiring for dense working lists.
- **Raw browser controls:** grey "Choose File" buttons, default selects and checkboxes. That's the first thing the eye lands on, on Jobs and People.
- **No hierarchy on long pages.** A person page is one long scroll of sections. There's no overview at the top and no way to jump to Career, Messages or Timeline.
- **No feedback or motion:**
  - actions reload silently;
  - there's no loading state, no confirmation and no hover response on rows;
  - you have to aim for the underlined name, because a row isn't clickable.
- **Tables don't adapt:** on a phone the jobs table squeezes into five narrow columns.
- **No starting point.** The home page is the jobs table. A recruiter starting the day wants to know who's waiting, what needs a decision, and who's going stale.

## Direction
Calm, dark and editorial, like the website, built as a modern tool. It should feel like Linear, Superhuman or Attio: fast, keyboard-friendly, quiet until something needs you. The brand shows in a few strong places (typewriter titles, amber accents, the split-flap nod), not on every word.

## In scope, in order
1. **Foundations: tokens and type.**
   - Colour, spacing, radius, shadow and motion tokens in one place.
   - Type:
     - Special Elite for page titles (the website's voice);
     - IBM Plex Sans for interface text (readable at small sizes);
     - IBM Plex Mono only for data (numbers, dates, IDs, counts) with tabular figures.
   - Band colours with meaning:
     - **Priority:** amber;
     - **Review later:** cool neutral;
     - **Do not submit:** muted red.
   - Focus rings everywhere; `prefers-reduced-motion` respected.
2. **App shell and navigation.**
   - A left sidebar, grouped:
     - **Work:** Today, Jobs, Inbox, People, Companies;
     - **Find:** Search, Refresh;
     - **Desk:** Import, Mailbox, Costs, Members.
   - Icons, the current page highlighted, and live counts (Inbox waiting, Refresh due).
   - It collapses to icons, and becomes a drawer on phones.
   - A slim top bar: breadcrumbs, the desk switcher, and your account menu.
3. **Find anything: the ⌘K command palette.**
   - From any page, type a name to jump to a person, job or company.
   - Or run an action: "New job from an ad", "Add CVs", "Go to inbox".
   - Keyboard shortcuts: `/` search, `g` then `j/i/p/c` to go to Jobs/Inbox/People/Companies, `j`/`k` to move through lists, `Enter` to open, `?` to show them all.
4. **Components.**
   - Buttons: primary, secondary, ghost and danger.
   - Drag-and-drop zones that replace every file input, with progress.
   - Styled selects, checkboxes and inputs.
   - Cards and band badges.
   - Tables with a sticky header, whole-row click and hover. On phones they become stacked cards.
   - Tabs, toasts for every action ("Approved", "Moved to Priority", with Undo where the action allows), empty states with a next step, and skeleton loading.
5. **Pages, most used first.**
   - **Today (new home):**
     - priority people waiting, per job;
     - inbox cards needing a decision;
     - who's going stale;
     - recent activity.

     The headline counts turn over like the website's split-flap board when they change.
   - **Job:**
     - a header with the company, stages and band counts;
     - bands as tabs instead of collapsible lists;
     - each person as a card with tier, reasons and gaps at a glance;
     - drop CVs anywhere on the page.
   - **Person:**
     - a header card (name, current role, location, freshness, tags, quick actions);
     - sticky section tabs: Overview, Career, Facts, Messages, Timeline, Documents;
     - facts to approve grouped with one-click Approve / Reject.
   - **Inbox:** one card at a time with keyboard decisions (`a` approve, `r` reject, `s` skip). Built for "in a roll", as with the Brief.
   - **People, Companies, Search, Refresh, Import, Mailbox, Costs, Members, Account, Sign-in:** the same system applied. The sign-in page gets the website's wordmark and intro feel.
6. **Motion, small and purposeful.**
   - Page transitions (a 150 ms fade/slide via the browser's View Transitions).
   - Lists stagger in on first load; hover lifts on cards.
   - A count changes with a flap.
   - Toasts slide in; tabs move with an underline.
   - Nothing over 250 ms, and nothing moves with reduced motion on.
7. **Proof.**
   - Screenshots of every page at desktop and phone width, before and after.
   - The accessibility test (every control has a name; keyboard reachable) still passes, and contrast meets WCAG AA.
   - The e2e suite updated to the new layout, run when credits are back (or with recordings).

## Decisions for the owner
1. **Interface font:** IBM Plex Sans for the working interface (with Plex Mono for data, Special Elite for titles), or everything monospace as today? *Recommendation: Plex Sans. Dense lists all day read much better in a proportional face; the brand stays in titles, numbers and accents.*
2. **Light mode:** dark only (like the website), or also a light theme you can switch to? *Recommendation: dark only now, with the tokens ready for light later.*
3. **Home:** a new **Today** page as the landing page, with Jobs one click away? *Recommendation: yes.*

## Out of scope
- The public website itself (already designed).
- New desk features: this is design, navigation and interaction only. No rules change, and nothing new is stored, except what the Today page reads from existing data.
