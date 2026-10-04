import { createContext } from "react";

/** Explicitly supplied by the composition that actually renders the toolbar. */
export const NavigationCapabilitiesContext = createContext({ home: false, back: false });
