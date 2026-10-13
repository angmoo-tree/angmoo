import "server-only";

/** HTML policy is owned by the Next server; static/Tauri has its own policy. */
export function htmlContentSecurityPolicy(nonce:string,development=false):string {
  if(!/^[A-Za-z0-9+/]{24,}={0,2}$/.test(nonce))throw new Error("csp_nonce_invalid");
  return [
    "default-src 'self'","base-uri 'self'","object-src 'none'","frame-ancestors 'none'","form-action 'self'",
    `script-src 'self' 'nonce-${nonce}' 'wasm-unsafe-eval'${development?" 'unsafe-eval'":""} https://accounts.google.com https://challenges.cloudflare.com`,
    "script-src-attr 'none'","style-src 'self' 'unsafe-inline' https://accounts.google.com",
    "img-src 'self' data: blob: https:","font-src 'self' data:",
    "connect-src 'self' https://accounts.google.com https://challenges.cloudflare.com",
    "frame-src https://accounts.google.com https://challenges.cloudflare.com","worker-src 'self' blob:",
  ].join("; ");
}
