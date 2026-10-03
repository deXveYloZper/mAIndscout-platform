// Streams an original document through the cockpit, so the browser never sees the operator token.
import { apiRaw } from "@/lib/api";

export async function GET(_: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  if (!/^[0-9a-f-]{36}$/i.test(id)) return new Response("Not found", { status: 404 });
  const upstream = await apiRaw(`/v1/documents/${id}/file`);
  return new Response(upstream.body, {
    headers: {
      "Content-Type": upstream.headers.get("Content-Type") ?? "application/octet-stream",
      "Content-Disposition": upstream.headers.get("Content-Disposition") ?? "inline",
      "Cache-Control": "private, no-store",
    },
  });
}
