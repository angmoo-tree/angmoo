import { proxyBackend } from "@/lib/backend";

export async function GET() {
  return proxyBackend("/api/v1/posts");
}
