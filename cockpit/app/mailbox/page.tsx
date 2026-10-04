import { connectMailbox, disconnectMailbox, syncMailbox } from "@/app/actions";
import { api, type MailboxStatus } from "@/lib/api";

export const metadata = { title: "Mailbox" };

const NAME = { google: "Gmail", microsoft: "Outlook" } as const;

export default async function Mailbox({ searchParams }: { searchParams: Promise<{ connected?: string; error?: string }> }) {
  const [{ connected, error }, box] = await Promise.all([searchParams, api<MailboxStatus>("/v1/mailbox")]);
  return (
    <>
      <h1>Mailbox</h1>
      <p className="sub">
        Connect your Gmail or Outlook so drafts land in your own drafts folder. The desk never sends: you read, edit and press send
        yourself. It also notices when a draft was sent and when someone replies, logs both on the timeline, and drafts a follow-up
        a few days after a message goes unanswered (stopped as soon as they reply).
      </p>
      {connected && <p className="ok" role="status">{NAME[connected as keyof typeof NAME] ?? connected} connected.</p>}
      {error && <p className="error" role="alert">Not connected: {error}</p>}

      {box.connected && box.provider ? (
        <section className="panel">
          <h3>{NAME[box.provider]}: {box.account}</h3>
          <p className="sub">
            {box.status === "connected" ? "Connected" : `Needs reconnecting (${box.status})`}
            {box.last_sync_at ? ` · last looked ${box.last_sync_at.slice(0, 16).replace("T", " ")}` : " · not looked yet"}
          </p>
          <div className="row">
            <form action={syncMailbox.bind(null, "/mailbox")}><button className="btn small">Look now</button></form>
            <form action={disconnectMailbox}><button className="btn small">Disconnect</button></form>
          </div>
          <p className="hint">Disconnecting deletes the stored sign-in. Drafts already in your mailbox stay there.</p>
        </section>
      ) : (
        <section className="panel">
          <h3>Connect a mailbox</h3>
          <div className="mailbox-providers">
            {(["google", "microsoft"] as const).map((p) => {
              const ready = p === "google" ? box.google_ready : box.microsoft_ready;
              return ready ? (
                <form key={p} action={connectMailbox.bind(null, p)}><button className="btn primary">Connect {NAME[p]}</button></form>
              ) : (
                <button key={p} className="btn" disabled title="Not set up yet: see the setup guide">Connect {NAME[p]} (not set up)</button>
              );
            })}
          </div>
          {!box.google_ready && !box.microsoft_ready && (
            <p className="hint">
              Neither is set up on this desk yet. Each needs a one-off app registration with Google or Microsoft; the steps are in
              docs/build/connections/mailbox-setup.md.
            </p>
          )}
          <p className="sub">Without a mailbox, drafts still work: copy the text into your email and mark it sent.</p>
        </section>
      )}
    </>
  );
}
