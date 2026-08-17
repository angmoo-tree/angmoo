import { redirect } from "next/navigation";

import { PRODUCT_ROUTES } from "@/shared/navigation/public";

export default function NewWorldPage() {
  redirect(PRODUCT_ROUTES.studioNewWorld);
}
