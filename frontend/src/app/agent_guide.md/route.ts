import { readAgentGuide } from "@/features/support/api/documents-server";

export async function GET(request:Request) {
  const language=new URL(request.url).searchParams.get("lang")??"ko";
  if(language!=="ko"&&language!=="en")return Response.json({detail:"guide_language_unsupported"},{status:400});
  const markdown = await readAgentGuide(language);
  return new Response(markdown, {
    headers: {
      "Cache-Control": "public, max-age=60",
      "Content-Type": "text/markdown; charset=utf-8",
    },
  });
}
