"use client";

import { useEffect } from "react";
import { reportClientError } from "@/app/actions";

// The last resort: an error in the desk's own frame (its sidebar, its layout) used to show the browser's bare
// "Application error: a client-side exception has occurred" (owner, 2026-10-22). Now a page that says what to do,
// and the error goes to the activity log.
export default function GlobalError({ error }: { error: Error & { digest?: string } }) {
  useEffect(() => {
    void reportClientError({ message: error.message || "unknown error", stack: error.stack, url: window.location.href, digest: error.digest });
  }, [error]);
  return (
    <html lang="en">
      <body style={{ fontFamily: "system-ui, sans-serif", background: "#111", color: "#eee", padding: "48px 24px" }}>
        <h1 style={{ fontWeight: 400 }}>The desk hit an error</h1>
        <p>It has been written to the activity log. Reloading usually brings the page back.</p>
        <p><button onClick={() => window.location.reload()} style={{ padding: "8px 16px", cursor: "pointer" }}>Reload the page</button>
          {" "}<a href="/activity?level=error" style={{ color: "#f0a020" }}>Open the activity log</a></p>
        {error.digest && <p style={{ opacity: 0.6, fontSize: 13 }}>Reference: {error.digest}</p>}
      </body>
    </html>
  );
}
