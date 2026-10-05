import type { Metadata } from "next";
import Link from "next/link";
import { signOut, switchDesk } from "@/app/actions";
import { currentUser } from "@/lib/api";
import "./globals.css";

// Every page shows live desk data: never pre-render at build time (CI has no API or session).
export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: { default: "Desk · mAIndscout", template: "%s · mAIndscout desk" },
  robots: { index: false, follow: false },
};

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const me = await currentUser();
  const ready = me && !me.needs_two_step;
  return (
    <html lang="en">
      <body>
        <a className="skip" href="#main">Skip to content</a>
        <header className="top">
          <Link href="/" className="brand">mAIndscout <span>desk</span></Link>
          {ready && (
            <nav>
              <Link href="/">Jobs</Link>
              <Link href="/people">People</Link>
              <Link href="/companies">Companies</Link>
              <Link href="/inbox">Inbox</Link>
              <Link href="/search">Search</Link>
              <Link href="/refresh">Refresh</Link>
              <Link href="/import">Import</Link>
              <Link href="/mailbox">Mailbox</Link>
              <Link href="/costs">Costs</Link>
              {me.role === "owner" && <Link href="/members">Members</Link>}
            </nav>
          )}
          {me && (
            <div className="row who">
              {me.desks.length > 1 && (
                <form action={switchDesk} className="row">
                  <select name="desk" defaultValue={me.desk} aria-label="Desk">
                    {me.desks.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
                  </select>
                  <button className="btn small">Switch</button>
                </form>
              )}
              <Link href="/account">{me.name}</Link>
              <form action={signOut}><button className="btn small ghost">Sign out</button></form>
            </div>
          )}
        </header>
        <main id="main">{children}</main>
      </body>
    </html>
  );
}
