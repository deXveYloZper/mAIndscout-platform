// Sign-in and one-time links: no navigation, one card on the website's dotted field.
export default function PublicLayout({ children }: { children: React.ReactNode }) {
  return (
    <main id="main" className="signin-page">
      <div className="signin">
        <span className="wordmark" aria-hidden="true">m<span className="ai">AI</span>ndscout</span>
        <p className="tagline">The desk</p>
        <div className="card">{children}</div>
      </div>
    </main>
  );
}
