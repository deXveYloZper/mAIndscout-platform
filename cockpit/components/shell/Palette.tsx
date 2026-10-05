"use client";

import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowRight, Briefcase, Building2, FilePlus2, Inbox, LayoutDashboard, RefreshCw, Search, Upload, User, Users,
} from "lucide-react";

type Hit = { id: string; name: string; meta?: string };
type Found = { people: Hit[]; jobs: Hit[]; companies: Hit[] };
type Option = { key: string; group: string; label: string; meta?: string; icon: React.ElementType; href: string };

const GO: Option[] = [
  { key: "go-today", group: "Go to", label: "Today", icon: LayoutDashboard, href: "/" },
  { key: "go-jobs", group: "Go to", label: "Jobs", icon: Briefcase, href: "/jobs" },
  { key: "go-inbox", group: "Go to", label: "Inbox", icon: Inbox, href: "/inbox" },
  { key: "go-people", group: "Go to", label: "People", icon: Users, href: "/people" },
  { key: "go-companies", group: "Go to", label: "Companies", icon: Building2, href: "/companies" },
  { key: "go-refresh", group: "Go to", label: "Refresh: who to re-contact", icon: RefreshCw, href: "/refresh" },
];
const ACT: Option[] = [
  { key: "act-job", group: "Actions", label: "New job from an advertisement", icon: FilePlus2, href: "/jobs#new" },
  { key: "act-cvs", group: "Actions", label: "Add CVs to the pool", icon: Upload, href: "/people#add" },
  { key: "act-search", group: "Actions", label: "Search in your own words", icon: Search, href: "/search" },
  { key: "act-import", group: "Actions", label: "Import from a CSV", icon: Upload, href: "/import" },
];

export function Palette({ onClose, owner }: { onClose: () => void; owner: boolean }) {
  const router = useRouter();
  const [q, setQ] = useState("");
  const [found, setFound] = useState<Found>({ people: [], jobs: [], companies: [] });
  const [active, setActive] = useState(0);
  const input = useRef<HTMLInputElement>(null);
  const list = useRef<HTMLUListElement>(null);

  useEffect(() => { input.current?.focus(); }, []);

  // Names as you type (debounced; the latest answer wins).
  useEffect(() => {
    const term = q.trim();
    if (term.length < 2) { setFound({ people: [], jobs: [], companies: [] }); return; }
    const ctl = new AbortController();
    const t = window.setTimeout(() => {
      fetch(`/lookup?q=${encodeURIComponent(term)}`, { signal: ctl.signal })
        .then((r) => (r.ok ? r.json() : { people: [], jobs: [], companies: [] }))
        .then(setFound)
        .catch(() => {});
    }, 140);
    return () => { ctl.abort(); window.clearTimeout(t); };
  }, [q]);

  const options = useMemo<Option[]>(() => {
    const term = q.trim().toLowerCase();
    const match = (o: Option) => !term || o.label.toLowerCase().includes(term);
    const named: Option[] = [
      ...found.people.map((h) => ({ key: `p-${h.id}`, group: "People", label: h.name, meta: h.meta, icon: User, href: `/people/${h.id}` })),
      ...found.jobs.map((h) => ({ key: `j-${h.id}`, group: "Jobs", label: h.name, meta: h.meta, icon: Briefcase, href: `/jobs/${h.id}` })),
      ...found.companies.map((h) => ({ key: `c-${h.id}`, group: "Companies", label: h.name, meta: h.meta, icon: Building2, href: `/companies/${h.id}` })),
    ];
    const go = GO.filter(match);
    const act = ACT.filter((o) => (owner || o.key !== "act-import") && match(o));
    const searchAll: Option[] = term.length >= 2
      ? [{ key: "search-q", group: "Search", label: `Search the desk for “${q.trim()}”`, icon: Search, href: `/search?q=${encodeURIComponent(q.trim())}` }]
      : [];
    return [...named, ...searchAll, ...go, ...act];
  }, [found, q, owner]);

  useEffect(() => { setActive(0); }, [options.length, q]);
  useEffect(() => {
    list.current?.querySelector<HTMLElement>(`[data-i="${active}"]`)?.scrollIntoView({ block: "nearest" });
  }, [active]);

  const open = (o: Option | undefined) => {
    if (!o) return;
    onClose();
    router.push(o.href);
  };

  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === "Escape") { e.preventDefault(); onClose(); }
    else if (e.key === "ArrowDown") { e.preventDefault(); setActive((a) => Math.min(a + 1, options.length - 1)); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setActive((a) => Math.max(a - 1, 0)); }
    else if (e.key === "Enter") { e.preventDefault(); open(options[active]); }
  };

  let lastGroup = "";
  return (
    <div className="palette-backdrop" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="palette" role="dialog" aria-modal="true" aria-label="Find anything" onKeyDown={onKey}>
        <div className="q">
          <Search aria-hidden="true" />
          <input ref={input} value={q} onChange={(e) => setQ(e.target.value)} placeholder="Type a name, or what you want to do…"
            aria-label="Find a person, job, company or action" role="combobox" aria-expanded="true" aria-controls="palette-list"
            aria-activedescendant={options[active] ? `opt-${options[active].key}` : undefined} />
          <kbd>Esc</kbd>
        </div>
        <ul id="palette-list" role="listbox" ref={list}>
          {options.length === 0 && <li className="none">Nothing matches “{q}”.</li>}
          {options.map((o, i) => {
            const header = o.group !== lastGroup ? <li className="grp" role="presentation" key={`g-${o.group}`}>{o.group}</li> : null;
            lastGroup = o.group;
            const Icon = o.icon;
            return [
              header,
              <li key={o.key} id={`opt-${o.key}`} data-i={i} role="option" aria-selected={i === active}
                onMouseMove={() => setActive(i)} onClick={() => open(o)}>
                <Icon aria-hidden="true" />
                <span>{o.label}</span>
                {o.meta ? <span className="meta">{o.meta}</span> : i === active ? <ArrowRight className="meta" aria-hidden="true" /> : null}
              </li>,
            ];
          })}
        </ul>
        <div className="foot"><span><kbd>↑</kbd> <kbd>↓</kbd> move</span><span><kbd>Enter</kbd> open</span><span><kbd>Esc</kbd> close</span></div>
      </div>
    </div>
  );
}
