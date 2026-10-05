import { inviteMember, removeMember, resetMember, setMemberRole } from "@/app/actions";
import { InviteForm, ResetButton } from "@/components/AccessForms";
import { api, type Me, type Member } from "@/lib/api";

export const metadata = { title: "Members" };

export default async function Members() {
  const me = await api<Me>("/v1/auth/me");
  if (me.role !== "owner") {
    return (
      <>
        <h1>Members</h1>
        <p className="sub">Only a desk owner manages members.</p>
      </>
    );
  }
  const members = await api<Member[]>("/v1/members");
  return (
    <>
      <h1>Members</h1>
      <p className="sub">
        Invite someone with a one-time link (valid 7 days). Nothing is emailed: copy the link and send it yourself. Owners
        manage members, the mailbox and import quotes; recruiters do everything else, including forgetting a person.
      </p>

      <section className="panel">
        <h3>Invite</h3>
        <InviteForm action={inviteMember} />
      </section>

      <table>
        <thead><tr><th>Name</th><th>Email</th><th>Role</th><th>Two-step</th><th></th></tr></thead>
        <tbody>
          {members.map((m) => (
            <tr key={m.id ?? `invite-${m.email}`}>
              <td>{m.name ?? <span className="sub">invited</span>}</td>
              <td>{m.email}</td>
              <td>
                {m.id && m.id !== me.id ? (
                  <form action={setMemberRole.bind(null, m.id)} className="row">
                    <select name="role" defaultValue={m.role} aria-label={`Role of ${m.email}`}>
                      <option value="recruiter">Recruiter</option>
                      <option value="owner">Owner</option>
                    </select>
                    <button className="btn small">Save</button>
                  </form>
                ) : m.role}
              </td>
              <td>{m.invited ? <span className="sub">until {m.expires_at?.slice(0, 10)}</span> : m.two_step ? "on" : "off"}</td>
              <td>
                {m.id && m.id !== me.id && (
                  <div className="row">
                    <ResetButton action={resetMember.bind(null, m.id)} name={m.email} />
                    <form action={removeMember.bind(null, m.id)}>
                      <button className="btn small danger" aria-label={`Remove ${m.email} from the desk`}>Remove</button>
                    </form>
                  </div>
                )}
                {m.id === me.id && <span className="sub">you</span>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}
