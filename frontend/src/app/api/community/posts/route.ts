import { proxyBackend } from "@/lib/server/backend";

export async function GET(request: Request) {
  return proxyBackend("/api/v1/posts", { signal: request.signal });
}
