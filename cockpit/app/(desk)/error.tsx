"use client";

import Link from "next/link";
import { AlertTriangle } from "lucide-react";

// Shown inside the desk (sidebar and search stay usable). Production builds hide the server's message on purpose.
export default function DeskError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  const hidden = /omitted in production/i.test(error.message);
  return (
    <section className="panel errorpanel" role="alert">
      <AlertTriangle aria-hidden="true" />
      <div>
        <h1>Something went wrong</h1>
        <p className="sub">
          {hidden ? "This page could not be loaded." : error.message || "The platform API did not answer."} Try again, or go back to{" "}
          <Link href="/">Today</Link>. If it keeps happening, check that the API is running.
        </p>
        <div className="row">
          <button className="btn primary" onClick={reset}>Try again</button>
          {error.digest && <span className="mini">Reference: {error.digest}</span>}
        </div>
      </div>
    </section>
  );
}
