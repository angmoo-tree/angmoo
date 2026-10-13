import config from "./playwright.comfy-security.config";
export default {...config,testMatch:"image-integration.spec.ts",grep:/Chat typing shows one pending indicator before any image stream result/,
 projects:[{name:"next",use:{baseURL:"http://127.0.0.1:3440"}}],reporter:[["list"],["json",{outputFile:"../artifacts/comfy-security-20261012/csp-stream.json"}]]};
