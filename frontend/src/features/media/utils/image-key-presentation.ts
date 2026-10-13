/** Media owns which providers have a generic service secret input. */
export const imageUsesServiceKey = (profile: { provider: string }) => profile.provider !== "comfyui";
