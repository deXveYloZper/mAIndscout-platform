"use client";

export default function Error({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <div className="panel">
      <h1>Something failed</h1>
      <p className="err">{error.message || "The platform API did not answer."}</p>
      <p className="sub">Is the API running (python -m maindscout serve) and is cockpit/.env.local filled in?</p>
      <button className="btn" onClick={reset}>Try again</button>
    </div>
  );
}
