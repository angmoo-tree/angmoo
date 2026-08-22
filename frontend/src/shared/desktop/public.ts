export { DesktopWindowBridge } from "./desktop-window-bridge";
export {
  consumeDesktopWindowBootstrapRoute,
  currentDesktopRoute,
  desktopWindowKindForRoute,
  getDesktopWindowState,
  getDesktopRuntimeStatus,
  isTauriDesktopRuntime,
  navigateCurrentDesktopRoute,
  normalizeInternalRoute,
  openDesktopProductWindow,
  retryDesktopRuntime,
  subscribeDesktopRoute,
} from "./product-window";
export type {
  AngmooDesktopWindowKind,
  AngmooDesktopWindowState,
  AngmooDesktopRuntimeStatus,
} from "./product-window";
