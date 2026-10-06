// ⌘K asks this as the user types; the cockpit's server calls the API with the signed-in session.
import { ApiError, apiRaw } from "@/lib/api";

export async function GET(request: Request) {
  const q = new URL(request.url).searchParams.get("q") ?? "";
  try {
    const res = await apiRaw(`/v1/lookup?q=${encodeURIComponent(q.slice(0, 200))}`);
    return new Response(res.body, { headers: { "Content-Type": "application/json", "Cache-Control": "private, no-store" } });
  } catch (e) {
    return Response.json({ people: [], jobs: [], companies: [] }, { status: e instanceof ApiError ? e.status : 500 });
  }
}
