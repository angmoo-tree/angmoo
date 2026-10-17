import { proxyMedia } from "@/lib/server/media";

type Context = { params: Promise<{ path: string[] }> };

async function media(request: Request, context: Context) {
  return proxyMedia(request, (await context.params).path);
}

export const GET = media;
export const HEAD = media;
