import { changePassword, confirmTwoStep, endOtherSessions, signOut, startTwoStep } from "@/app/actions";
import { PasswordForm, TwoStepSetup } from "@/components/AccessForms";
import { api, type Me } from "@/lib/api";

export const metadata = { title: "Account" };

export default async function Account({ searchParams }: { searchParams: Promise<{ setup?: string; two_step?: string }> }) {
  const [params, me] = await Promise.all([searchParams, api<Me>("/v1/auth/me")]);
  return (
    <>
      <h1>{me.name}</h1>
      <p className="sub">{me.email} · {me.role} of {me.desks.find((d) => d.id === me.desk)?.name ?? "this desk"}</p>

      {me.needs_two_step && (
        <div className="warn">Owners need two-step verification. Set it up below; the rest of the desk opens once it is on.</div>
      )}
      {params.two_step === "on" && <p className="ok" role="status">Two-step verification is on.</p>}

      <section className="panel">
        <h3>Two-step verification</h3>
        {me.two_step
          ? <p>On. Each sign-in asks for a code from your authenticator app. Lost your phone? Ask an owner for a new sign-in link.</p>
          : <TwoStepSetup start={startTwoStep} confirm={confirmTwoStep} />}
      </section>

      <section className="panel">
        <h3>Password</h3>
        <PasswordForm action={changePassword} />
      </section>

      <section className="panel">
        <h3>Sessions</h3>
        <div className="row">
          <form action={endOtherSessions}><button className="btn">Sign out everywhere else</button></form>
          <form action={signOut}><button className="btn">Sign out</button></form>
        </div>
      </section>
    </>
  );
}
