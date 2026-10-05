import { NextResponse, type NextRequest } from "next/server";

// Without a session cookie, every page goes to sign-in. This is only for a smooth experience: the API checks every
// request itself, so a forged or stale cookie gets nothing.
const OPEN = ["/login", "/invite/"];

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;
  if (OPEN.some((p) => pathname === p || pathname.startsWith(p))) return NextResponse.next();
  if (request.cookies.get("ms_session")?.value) return NextResponse.next();
  const url = request.nextUrl.clone();
  url.pathname = "/login";
  url.search = "";
  return NextResponse.redirect(url);
}

export const config = { matcher: ["/((?!_next/|favicon.ico).*)"] };
