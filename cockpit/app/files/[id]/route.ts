// Streams an original document through the cockpit, so the browser never sees the operator token.
import { apiRaw } from "@/lib/api";

// Only these open in the browser; anything else downloads (an uploaded HTML or SVG must never run on the desk's origin).
const INLINE = ["application/pdf", "text/plain"];

export async function GET(_: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  if (!/^[0-9a-f-]{36}$/i.test(id)) return new Response("Not found", { status: 404 });
  const upstream = await apiRaw(`/v1/documents/${id}/file`);
  const type = upstream.headers.get("Content-Type") ?? "application/octet-stream";
  const inline = INLINE.some((t) => type.startsWith(t));
  const disposition = upstream.headers.get("Content-Disposition") ?? "attachment";
  const headers: Record<string, string> = {
    "Content-Type": inline ? type : "application/octet-stream",
    "Content-Disposition": inline ? disposition : disposition.replace(/^inline/, "attachment"),
    "X-Content-Type-Options": "nosniff",
    "Cache-Control": "private, no-store",
  };
  if (!type.startsWith("application/pdf")) headers["Content-Security-Policy"] = "sandbox; default-src 'none'";
  return new Response(upstream.body, { headers });
}
