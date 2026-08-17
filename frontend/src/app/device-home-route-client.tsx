"use client";

import { useAuth } from "@/components/auth-provider";
import { DeviceHome } from "@/features/device-home/public";


export function DeviceHomeRouteClient() {
  const { status } = useAuth();
  return <DeviceHome authStatus={status} />;
}
