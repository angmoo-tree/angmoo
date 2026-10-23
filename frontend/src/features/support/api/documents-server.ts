import "server-only";
import { readFile } from "fs/promises";
import path from "path";

export function getAgentGuidePath(language:"ko"|"en"="ko") {
  if(language==="en")return path.join(process.cwd(),"..","docs","agent_guide.md");
  if(language==="ko")return path.join(process.cwd(),"..","docs","agent_guide.ko.md");
  throw new Error("guide_language_unsupported");
}

export function getOpenApiPath() {
  return path.join(process.cwd(), "public", "openapi.json");
}

export function readAgentGuide(language:"ko"|"en"="ko") {
  // Literal reads keep Next's packaging trace limited to the two public guides.
  if(language==="en")return readFile(path.join(process.cwd(),"..","docs","agent_guide.md"),"utf8");
  if(language==="ko")return readFile(path.join(process.cwd(),"..","docs","agent_guide.ko.md"),"utf8");
  throw new Error("guide_language_unsupported");
}

export function readOpenApiSpec() {
  return readFile(getOpenApiPath(), "utf8");
}
