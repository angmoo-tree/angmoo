type LeaveGuard = () => boolean;
const guards = new Set<LeaveGuard>();
let unloadApprovedUntil = 0;

/** Owners register a confirmation callback, never their draft or credentials. */
export function registerProductLeaveGuard(guard: LeaveGuard) {
  guards.add(guard);
  return () => { guards.delete(guard); };
}

export function confirmProductLeave() {
  return [...guards].every(guard => guard());
}

export function approveProductUnload() { unloadApprovedUntil = Date.now() + 1000; }
export function isProductUnloadApproved() { return Date.now() < unloadApprovedUntil; }
