import config from "./playwright.world-feed-ui.config";
export default {...config, testMatch:["world-feed-ui.spec.ts","world-social-output.spec.ts"],
  outputDir:"../artifacts/world-ui-sns-output-integration-20261005/next",
  reporter:[["list"],["json",{outputFile:"../artifacts/world-ui-sns-output-integration-20261005/next-results.json"}]]};
