import { redirect } from "next/navigation";

import {
  PRODUCT_ROUTES,
  productRouteWithSearchParams,
  type ProductRouteSearchParams,
} from "@/shared/navigation/public";

type PageProps = {
  searchParams: Promise<ProductRouteSearchParams>;
};

export default async function NewWorldPage({ searchParams }: PageProps) {
  redirect(
    productRouteWithSearchParams(
      PRODUCT_ROUTES.studioNewWorld,
      await searchParams,
    ),
  );
}
