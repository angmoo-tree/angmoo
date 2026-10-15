/** Same-origin ordinary link activation, after leave guards accept navigation. */
export const PRODUCT_LINK_ADMITTED_EVENT = "angmoo:product-link-admitted";
export function notifyProductLinkAdmission(anchor: HTMLAnchorElement) {
  window.dispatchEvent(new CustomEvent(PRODUCT_LINK_ADMITTED_EVENT, { detail: anchor }));
}
