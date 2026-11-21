import { NextResponse, type NextRequest } from "next/server";

// Next.js 16 "Proxy" (formerly Middleware). Optimistic UX redirect only: send visitors without a
// session cookie to /login. Real authentication and every permission check happen in FastAPI.
export function proxy(request: NextRequest) {
  if (["/docs", "/images/docs-garment-factory.webp"].includes(request.nextUrl.pathname)) return NextResponse.next();
  if (!request.cookies.has("te_session")) {
    return NextResponse.redirect(new URL("/login", request.url));
  }
  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!login|api|health|_next|favicon.ico|mockServiceWorker.js).*)"],
};
