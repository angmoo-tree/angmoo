import { proxyBackend } from "@/lib/backend";

type RouteContext = {
  params: Promise<{
    postId: string;
  }>;
};

export async function GET(_: Request, context: RouteContext) {
  const { postId } = await context.params;

  return proxyBackend(`/api/v1/posts/${postId}`);
}
