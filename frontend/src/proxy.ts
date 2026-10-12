import {randomBytes} from "node:crypto";
import {NextResponse,type NextRequest} from "next/server";
import {htmlContentSecurityPolicy} from "@/lib/security/csp";

export function proxy(request:NextRequest) {
  const nonce=randomBytes(18).toString("base64");
  const policy=htmlContentSecurityPolicy(nonce,process.env.NODE_ENV==="development");
  const headers=new Headers(request.headers);
  headers.set("x-nonce",nonce);
  headers.set("Content-Security-Policy",policy);
  const response=NextResponse.next({request:{headers}});
  response.headers.set("Content-Security-Policy",policy);
  response.headers.set("Cache-Control","private, no-store");
  response.headers.set("X-Content-Type-Options","nosniff");
  return response;
}

// Exempt known resources, not arbitrary extensions: /agents/name.json and
// unknown .md/.svg URLs can still render HTML and must keep the policy.
export const config={matcher:["/((?!api/|_next/|media/|(?:agent_guide\\.md|openapi\\.json|manifest\\.webmanifest|favicon\\.ico|icon\\.svg|robots\\.txt|sitemap\\.xml|sw\\.js|world-default-banner\\.svg|pwa-icon-192\\.png|pwa-icon-512\\.png|pwa-maskable-512\\.png|opengraph-image)$).*)"]};
