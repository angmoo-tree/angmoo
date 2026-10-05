import config from "./playwright.world-feed-ui.config";
export default {...config, testMatch:"world-social-backend.spec.ts",
  outputDir:"../artifacts/world-ui-sns-output-integration-20261005/backend-browser",
  reporter:[["list"],["json",{outputFile:"../artifacts/world-ui-sns-output-integration-20261005/backend-browser-results.json"}]],
  projects:[{name:"next-production",use:{baseURL:"http://127.0.0.1:3340"}}],
  webServer:[
    {command:"node ../frontend/scripts/serve-production.mjs --port 3340",env:{ANGMOO_API_BASE_URL:"http://127.0.0.1:3342"},url:"http://127.0.0.1:3340",reuseExistingServer:false,timeout:90000},
    {command:process.platform==="win32"?'"..\\backend\\.venv\\Scripts\\python.exe" world-social-backend-fixture.py':"../backend/.venv/bin/python world-social-backend-fixture.py",url:"http://127.0.0.1:3342/fixture/evidence",reuseExistingServer:false,timeout:90000}
  ]};
