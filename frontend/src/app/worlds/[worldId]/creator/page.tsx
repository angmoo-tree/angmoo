import { redirect } from "next/navigation";

import {
  productRouteWithSearchParams,
  studioWorldRoute,
  type ProductRouteSearchParams,
} from "@/shared/navigation/public";

type PageProps = {
  params: Promise<{ worldId: string }>;
  searchParams: Promise<ProductRouteSearchParams>;
};

export default async function WorldCreatorPage({
  params,
  searchParams,
}: PageProps) {
  const [{ worldId }, resolvedSearchParams] = await Promise.all([
    params,
    searchParams,
  ]);
  redirect(
    productRouteWithSearchParams(
      studioWorldRoute(worldId),
      resolvedSearchParams,
    ),
  );
}
