import type { Metadata } from "next";
import { IBM_Plex_Mono, IBM_Plex_Sans } from "next/font/google";
import "./globals.css";

// Every page shows live desk data: never pre-render at build time (CI has no API or session).
export const dynamic = "force-dynamic";

// One type system with the website (owner, 2026-10-15): Plex Sans for titles and working text, Plex Mono for data.
const sans = IBM_Plex_Sans({ weight: ["300", "400", "500", "600"], subsets: ["latin", "latin-ext"], variable: "--font-sans", display: "swap" });
const mono = IBM_Plex_Mono({ weight: ["400", "500"], subsets: ["latin", "latin-ext"], variable: "--font-mono-face", display: "swap" });

export const metadata: Metadata = {
  title: { default: "Desk · mAIndscout", template: "%s · mAIndscout desk" },
  robots: { index: false, follow: false },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${sans.variable} ${mono.variable}`}>
      <body>
        <a className="skip" href="#main">Skip to content</a>
        {children}
      </body>
    </html>
  );
}
