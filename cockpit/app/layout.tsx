import type { Metadata } from "next";
import { IBM_Plex_Mono, IBM_Plex_Sans, Special_Elite } from "next/font/google";
import "./globals.css";

// Every page shows live desk data: never pre-render at build time (CI has no API or session).
export const dynamic = "force-dynamic";

// The website's voice for titles (Special Elite), a readable face for working text (Plex Sans), Plex Mono for data.
const sans = IBM_Plex_Sans({ weight: ["400", "500", "600"], subsets: ["latin", "latin-ext"], variable: "--font-sans", display: "swap" });
const mono = IBM_Plex_Mono({ weight: ["400", "500"], subsets: ["latin", "latin-ext"], variable: "--font-mono-face", display: "swap" });
const display = Special_Elite({ weight: "400", subsets: ["latin"], variable: "--font-display-face", display: "swap" });

export const metadata: Metadata = {
  title: { default: "Desk · mAIndscout", template: "%s · mAIndscout desk" },
  robots: { index: false, follow: false },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${sans.variable} ${mono.variable} ${display.variable}`}>
      <body>
        <a className="skip" href="#main">Skip to content</a>
        {children}
      </body>
    </html>
  );
}
