import { proxyBackend } from "@/lib/backend";

type RouteContext = {
  params: Promise<{
    characterId: string;
  }>;
};

export async function GET(_: Request, context: RouteContext) {
  const { characterId } = await context.params;

  return proxyBackend(`/api/v1/characters/${characterId}/activity`);
}
