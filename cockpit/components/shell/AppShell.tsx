"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  Briefcase, Building2, ChevronsLeft, ChevronsRight, Coins, Inbox, LayoutDashboard, LogOut, Mail, Menu, RefreshCw,
  Search, Settings, Upload, UserCog, Users,
} from "lucide-react";
import { signOut, switchDesk } from "@/app/actions";
import type { Me } from "@/lib/api";
import { Palette } from "./Palette";
import { Shortcuts } from "./Shortcuts";

type Item = { href: string; label: string; icon: React.ElementType; count?: number; owner?: boolean };

function groups(inbox: number): { label: string; items: Item[] }[] {
  return [
    { label: "Work", items: [
      { href: "/", label: "Today", icon: LayoutDashboard },
      { href: "/jobs", label: "Jobs", icon: Briefcase },
      { href: "/inbox", label: "Inbox", icon: Inbox, count: inbox },
      { href: "/people", label: "People", icon: Users },
      { href: "/companies", label: "Companies", icon: Building2 },
    ] },
    { label: "Find", items: [
      { href: "/search", label: "Search", icon: Search },
      { href: "/refresh", label: "Refresh", icon: RefreshCw },
    ] },
    { label: "Desk", items: [
      { href: "/import", label: "Import", icon: Upload },
      { href: "/mailbox", label: "Mailbox", icon: Mail },
      { href: "/costs", label: "Costs", icon: Coins },
      { href: "/members", label: "Members", icon: UserCog, owner: true },
    ] },
  ];
}

function isActive(pathname: string, href: string): boolean {
  return href === "/" ? pathname === "/" : pathname === href || pathname.startsWith(`${href}/`);
}

function initials(name: string): string {
  return name.split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0]!.toUpperCase()).join("") || "?";
}

export function AppShell({ me, counts, children }: { me: Me; counts: { inbox: number }; children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [collapsed, setCollapsed] = useState(false);
  const [drawer, setDrawer] = useState(false);
  const [palette, setPalette] = useState(false);
  const [help, setHelp] = useState(false);
  const [menu, setMenu] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  // A remembered preference only; the page works without it.
  useEffect(() => {
    try { setCollapsed(localStorage.getItem("desk.sidebar") === "collapsed"); } catch {}
  }, []);
  const toggleCollapsed = () => {
    setCollapsed((c) => {
      try { localStorage.setItem("desk.sidebar", c ? "open" : "collapsed"); } catch {}
      return !c;
    });
  };

  useEffect(() => { setDrawer(false); setMenu(false); }, [pathname]);

  useEffect(() => {
    if (!menu) return;
    const close = (e: MouseEvent) => { if (!menuRef.current?.contains(e.target as Node)) setMenu(false); };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [menu]);

  // Keyboard: ⌘K / Ctrl+K or "/" find anything; "g" then a letter goes somewhere; "?" lists the shortcuts.
  const pending = useRef<number | null>(null);
  const onKey = useCallback((e: KeyboardEvent) => {
    const typing = e.target instanceof HTMLElement && (e.target.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName));
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") { e.preventDefault(); setPalette((p) => !p); return; }
    if (typing || e.metaKey || e.ctrlKey || e.altKey) return;
    if (e.key === "/") { e.preventDefault(); setPalette(true); return; }
    if (e.key === "?") { e.preventDefault(); setHelp(true); return; }
    if (e.key === "g") { pending.current = window.setTimeout(() => { pending.current = null; }, 900); return; }
    if (pending.current !== null) {
      const to = ({ t: "/", j: "/jobs", i: "/inbox", p: "/people", c: "/companies", s: "/search", r: "/refresh" } as Record<string, string>)[e.key];
      window.clearTimeout(pending.current);
      pending.current = null;
      if (to) { e.preventDefault(); router.push(to); }
    }
  }, [router]);
  useEffect(() => {
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onKey]);

  const desk = me.desks.find((d) => d.id === me.desk);
  return (
    <div className={`app${collapsed ? " collapsed" : ""}${drawer ? " drawer" : ""}`}>
      <div className="rail">
      <aside className="sidebar" aria-label="Desk navigation">
        <Link href="/" className="brandmark" aria-label="mAIndscout desk, Today">
          <span className="mark" aria-hidden="true">m</span>
          <span className="text">
            <span className="word">m<span className="ai">AI</span>ndscout</span>
            <span className="desk" style={{ display: "block" }}>
              {desk && desk.name.toLowerCase() !== "maindscout" ? desk.name : "the desk"}
            </span>
          </span>
        </Link>
        <nav>
          {groups(counts.inbox).map((g) => (
            <div className="navgroup" key={g.label}>
              <span>{g.label}</span>
              {g.items.filter((i) => !i.owner || me.role === "owner").map((i) => {
                const Icon = i.icon;
                const active = isActive(pathname, i.href);
                return (
                  <Link key={i.href} href={i.href} className={`navlink${i.count ? " has-count" : ""}`}
                    aria-current={active ? "page" : undefined} title={collapsed ? i.label : undefined}>
                    <Icon aria-hidden="true" />
                    <span>{i.label}</span>
                    {i.count ? <em className="count" aria-label={`${i.count} waiting`} style={{ fontStyle: "normal" }}>{i.count > 99 ? "99+" : i.count}</em> : null}
                  </Link>
                );
              })}
            </div>
          ))}
        </nav>
        <div className="sidebar-foot">
          <Link href="/account" className="navlink" aria-current={isActive(pathname, "/account") ? "page" : undefined}>
            <Settings aria-hidden="true" /><span>Account</span>
          </Link>
          <button type="button" className="navlink collapse-btn" onClick={toggleCollapsed}
            aria-label={collapsed ? "Expand the sidebar" : "Collapse the sidebar"}>
            {collapsed ? <ChevronsRight aria-hidden="true" /> : <ChevronsLeft aria-hidden="true" />}<span>Collapse</span>
          </button>
        </div>
      </aside>
      </div>
      <div className="scrim" onClick={() => setDrawer(false)} aria-hidden="true" />

      <div className="content">
        <header className="topbar">
          <button type="button" className="btn ghost menu-btn" onClick={() => setDrawer(true)} aria-label="Open navigation">
            <Menu aria-hidden="true" />
          </button>
          <button type="button" className="findbar" onClick={() => setPalette(true)} aria-label="Find a person, job or company (Ctrl K)">
            <Search aria-hidden="true" />
            <span>Find a person, job or company…</span>
            <kbd>Ctrl K</kbd>
          </button>
          <span className="spacer" />
          <div className="usermenu" ref={menuRef}>
            <button type="button" className="avatar" onClick={() => setMenu((m) => !m)} aria-haspopup="menu" aria-expanded={menu}
              aria-label={`Account menu for ${me.name}`}>
              {initials(me.name)}
            </button>
            {menu && (
              <div className="menu" role="menu">
                <div className="who-line">
                  <strong>{me.name}</strong>
                  <span className="mini">{me.email} · {me.role}</span>
                </div>
                {me.desks.length > 1 && (
                  <form action={switchDesk}>
                    <select name="desk" defaultValue={me.desk} aria-label="Desk" onChange={(e) => e.currentTarget.form?.requestSubmit()}>
                      {me.desks.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
                    </select>
                  </form>
                )}
                <Link href="/account" role="menuitem"><Settings aria-hidden="true" />Account and security</Link>
                {me.role === "owner" && <Link href="/members" role="menuitem"><UserCog aria-hidden="true" />Members</Link>}
                <button type="button" role="menuitem" onClick={() => { setMenu(false); setHelp(true); }}>
                  <span aria-hidden="true" style={{ width: 16, textAlign: "center" }}>?</span>Keyboard shortcuts
                </button>
                <form action={signOut}>
                  <button role="menuitem"><LogOut aria-hidden="true" />Sign out</button>
                </form>
              </div>
            )}
          </div>
        </header>
        <main id="main">{children}</main>
      </div>

      {palette && <Palette onClose={() => setPalette(false)} owner={me.role === "owner"} />}
      {help && <Shortcuts onClose={() => setHelp(false)} />}
    </div>
  );
}
