import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

// Every page shows live desk data: never pre-render at build time (CI has no API or token).
export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: { default: "Desk · mAIndscout", template: "%s · mAIndscout desk" },
  robots: { index: false, follow: false },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <a className="skip" href="#main">Skip to content</a>
        <header className="top">
          <Link href="/" className="brand">mAIndscout <span>desk</span></Link>
          <nav>
            <Link href="/">Jobs</Link>
            <Link href="/inbox">Inbox</Link>
          </nav>
        </header>
        <main id="main">{children}</main>
      </body>
    </html>
  );
}
