import { acceptInvite } from "@/app/actions";
import { AcceptForm } from "@/components/AccessForms";
import { ApiError, apiPublic } from "@/lib/api";

export const metadata = { title: "Join the desk" };

type Info = { email: string; desk: string; purpose: "invite" | "reset"; role: string; has_account: boolean };

export default async function Invite({ params }: { params: Promise<{ token: string }> }) {
  const { token } = await params;
  let info: Info;
  try {
    info = await apiPublic<Info>(`/v1/auth/invites/${encodeURIComponent(token)}`);
  } catch (e) {
    return (
      <section>
        <h1>This link doesn't work</h1>
        <p className="err">{e instanceof ApiError ? e.message : "The platform did not answer."}</p>
      </section>
    );
  }
  const reset = info.purpose === "reset";
  return (
    <section>
      <h1>{reset ? "Set a new password" : `Join ${info.desk}`}</h1>
      <p className="sub">
        {reset ? <>For {info.email}. Two-step verification is switched off and can be set up again after you sign in.</>
          : info.has_account ? <>{info.email} already has an account: enter its password to join as a {info.role}.</>
          : <>For {info.email}, as a {info.role}.</>}
      </p>
      <AcceptForm action={acceptInvite.bind(null, token)} needsName={!reset && !info.has_account} existing={info.has_account} reset={reset} />
    </section>
  );
}
