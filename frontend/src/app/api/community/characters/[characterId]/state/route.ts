import { proxyBackend } from "@/lib/backend";

type RouteContext = {
  params: Promise<{
    characterId: string;
  }>;
};

export async function POST(request: Request, context: RouteContext) {
  const { characterId } = await context.params;
  const body = await request.text();
  const authorization = request.headers.get("authorization");

  return proxyBackend(`/api/v1/characters/${characterId}/state`, {
    method: "POST",
    body,
    headers: {
      ...(authorization ? { Authorization: authorization } : {}),
      "Content-Type": "application/json",
    },
  });
}
