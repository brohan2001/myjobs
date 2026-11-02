import { timingSafeEqual } from "node:crypto";
import { NextRequest, NextResponse } from "next/server";

// /admin sits behind HTTP Basic auth: user "admin", password ADMIN_TOKEN (D31). The admin API checks the same token,
// so this only keeps the pages themselves private.
export const config = { matcher: ["/admin", "/admin/:path*"], runtime: "nodejs" };

function sameSecret(a: string, b: string): boolean {
  const x = Buffer.from(a);
  const y = Buffer.from(b);
  return x.length === y.length && timingSafeEqual(x, y);
}

export function middleware(req: NextRequest) {
  const token = process.env.ADMIN_TOKEN;
  if (!token) {
    return new NextResponse("Not found", { status: 404 });
  }
  const [scheme, encoded] = (req.headers.get("authorization") ?? "").split(" ");
  if (scheme === "Basic" && encoded) {
    const decoded = Buffer.from(encoded, "base64").toString();
    const sep = decoded.indexOf(":");
    if (decoded.slice(0, sep) === "admin" && sameSecret(decoded.slice(sep + 1), token)) {
      return NextResponse.next();
    }
  }
  return new NextResponse("Login required", {
    status: 401,
    headers: { "WWW-Authenticate": 'Basic realm="myjobs admin", charset="UTF-8"' },
  });
}
