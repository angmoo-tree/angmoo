export { DesktopWindowBridge } from "./desktop-window-bridge";
export {
  consumeDesktopWindowBootstrapRoute,
  canonicalProductRoute,
  currentDesktopRoute,
  desktopWindowKindForRoute,
  getDesktopWindowState,
  getDesktopRuntimeStatus,
  isTauriDesktopRuntime,
  navigateBackCurrentDesktopRoute,
  navigateCurrentDesktopRoute,
  navigateDesktopProductRoute,
  normalizeInternalRoute,
  openDesktopProductWindow,
  retryDesktopRuntime,
  subscribeDesktopRoute,
} from "./product-window";
export type {
  AngmooDesktopWindowKind,
  AngmooDesktopWindowState,
  AngmooDesktopRuntimeStatus,
  DesktopProductNavigationResult,
} from "./product-window";
