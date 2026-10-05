import { redirect } from "next/navigation";
import { AppShell } from "@/components/shell/AppShell";
import { apiOptional, currentUser } from "@/lib/api";

// Every desk page: the sidebar, the top bar, ⌘K and keyboard shortcuts. Signed-out visitors go to sign-in.
export default async function DeskLayout({ children }: { children: React.ReactNode }) {
  const me = await currentUser();
  if (!me) redirect("/login");
  const counts = (await apiOptional<{ inbox: number }>("/v1/nav")) ?? { inbox: 0 };
  return <AppShell me={me} counts={counts}>{children}</AppShell>;
}
