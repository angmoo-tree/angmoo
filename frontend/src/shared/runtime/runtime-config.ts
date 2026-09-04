export {
  DESKTOP_RUNTIME_CONFIG_CHANGED_EVENT,
  RuntimeFetchError,
  clearDesktopRuntimeConfig,
  getRuntimeConfig,
  installDesktopRuntimeConfig,
  isStaticFrontendProfile,
  resolveRuntimeMediaUrl,
  resolveRuntimeRequestUrl,
  runtimeFetch,
} from "@/lib/runtime/runtime-config";
export type {
  AngmooRuntimeConfig,
  RuntimeFetchErrorCode,
} from "@/lib/runtime/runtime-config";
