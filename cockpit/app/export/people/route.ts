// The desk's own people as CSV, through the cockpit (the browser never sees the operator token). Always free.
import { apiRaw } from "@/lib/api";

export async function GET() {
  const upstream = await apiRaw("/v1/export/people.csv");
  return new Response(upstream.body, {
    headers: {
      "Content-Type": "text/csv; charset=utf-8",
      "Content-Disposition": 'attachment; filename="maindscout-people.csv"',
      "Cache-Control": "private, no-store",
    },
  });
}
