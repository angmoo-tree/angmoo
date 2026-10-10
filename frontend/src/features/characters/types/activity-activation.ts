/** The existing activity editor owns validation, requests and scope lifetime. */
export type ActivityActivation = {
  enabled: boolean;
  canEnable: boolean;
  busy: boolean;
  reason: string | null;
  enable: () => Promise<boolean>;
};
