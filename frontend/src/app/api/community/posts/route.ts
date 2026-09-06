import { proxyBackend } from "@/lib/server/backend";

export async function GET() {
  return proxyBackend("/api/v1/posts");
}
