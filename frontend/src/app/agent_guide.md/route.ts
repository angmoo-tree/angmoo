import { readAgentGuide } from "@/features/support/api/documents-server";

export async function GET() {
  const markdown = await readAgentGuide();
  return new Response(markdown, {
    headers: {
      "Cache-Control": "public, max-age=60",
      "Content-Type": "text/markdown; charset=utf-8",
    },
  });
}
