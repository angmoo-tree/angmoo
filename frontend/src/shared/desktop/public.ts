export { DesktopWindowBridge } from "./desktop-window-bridge";
export {
  consumeDesktopWindowBootstrapRoute,
  canonicalProductRoute,
  currentDesktopRoute,
  desktopWindowKindForRoute,
  getDesktopWindowState,
  getDesktopRuntimeStatus,
  getDesktopShutdownStatus,
  skipDesktopMemoryShutdown,
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
  DesktopShutdownStatus,
  DesktopProductNavigationResult,
} from "./product-window";
