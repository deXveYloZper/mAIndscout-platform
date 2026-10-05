import { cookies } from "next/headers";
import { signIn, signInCode } from "@/app/actions";
import { CodeForm, SignInForm } from "@/components/AccessForms";
import { TICKET_COOKIE } from "@/lib/api";

export const metadata = { title: "Sign in" };

export default async function Login({ searchParams }: { searchParams: Promise<{ step?: string; ended?: string; ready?: string }> }) {
  const params = await searchParams;
  const code = params.step === "code" && (await cookies()).get(TICKET_COOKIE)?.value;
  return (
    <section className="signin">
      <h1>Sign in</h1>
      {params.ended && <p className="sub">Your session has ended. Sign in again.</p>}
      {params.ready && <p className="ok">Done. Sign in with your new password.</p>}
      {code ? <CodeForm action={signInCode} /> : <SignInForm action={signIn} />}
      <p className="hint">Forgot your password? Ask the desk owner for a new sign-in link.</p>
    </section>
  );
}
