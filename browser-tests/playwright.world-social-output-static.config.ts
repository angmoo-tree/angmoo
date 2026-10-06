import config from "./playwright.world-feed-ui-static.config";
export default {...config, testMatch:["world-feed-ui.spec.ts","world-social-output.spec.ts"],
  outputDir:"../artifacts/world-ui-sns-output-integration-20261005/static",
  reporter:[["list"],["json",{outputFile:"../artifacts/world-ui-sns-output-integration-20261005/static-results.json"}]]};
