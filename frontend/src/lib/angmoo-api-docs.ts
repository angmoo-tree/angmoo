import { readFile } from "fs/promises";
import path from "path";

export function getAgentGuidePath() {
  return path.join(process.cwd(), "..", "docs", "agent_guide.md");
}

export function getOpenApiPath() {
  return path.join(process.cwd(), "public", "openapi.json");
}

export function readAgentGuide() {
  return readFile(getAgentGuidePath(), "utf8");
}

export function readOpenApiSpec() {
  return readFile(getOpenApiPath(), "utf8");
}
