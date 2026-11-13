import { NextRequest, NextResponse } from "next/server";

/** Minimal request line for live debugging (docker logs asante-asante-1). */
export function middleware(request: NextRequest) {
  const { method } = request;
  const path = request.nextUrl.pathname;
  const search = request.nextUrl.search;
  console.info(`[asante] ${method} ${path}${search}`);
  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
