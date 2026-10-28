"use client";

import Link from "next/link";
import { useEffect } from "react";
import { AlertTriangle } from "lucide-react";
import { reportClientError } from "@/app/actions";

// Shown inside the desk (sidebar and search stay usable). Production builds hide the server's message on purpose.
// Every crash is reported to the activity log, so it can be read later (owner, 2026-10-22).
export default function DeskError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  const hidden = /omitted in production/i.test(error.message);
  useEffect(() => {
    void reportClientError({ message: error.message || "unknown error", stack: error.stack, url: window.location.href, digest: error.digest });
  }, [error]);
  return (
    <section className="panel errorpanel" role="alert">
      <AlertTriangle aria-hidden="true" />
      <div>
        <h1>Something went wrong</h1>
        <p className="sub">
          {hidden ? "This page could not be loaded." : error.message || "The platform API did not answer."} Try again, or go back to{" "}
          <Link href="/">Today</Link>. What happened is in the <Link href="/activity?level=error">activity log</Link>.
        </p>
        <div className="row">
          <button className="btn primary" onClick={reset}>Try again</button>
          <button className="btn" onClick={() => window.location.reload()}>Reload the page</button>
          {error.digest && <span className="mini">Reference: {error.digest}</span>}
        </div>
      </div>
    </section>
  );
}
