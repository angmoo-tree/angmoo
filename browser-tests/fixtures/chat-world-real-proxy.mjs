// No fake API responses: this front door forwards to the marked, synthetic-only
// contributor backend and serves the same built frontend as ordinary Next.
import {createServer, request as proxyRequest} from "node:http";
createServer((request,response)=>{
  const api=request.url.startsWith("/api/backend/");
  const media=request.url.startsWith("/media/");
  const port=api||media?3420:3415;
  const path=api?request.url.replace(/^\/api\/backend\//,"/api/v1/"):request.url;
  const forwarded=proxyRequest(`http://127.0.0.1:${port}${path}`,{method:request.method,headers:request.headers},result=>{
    response.writeHead(result.statusCode,result.headers);result.pipe(response);
  });
  forwarded.on("error",()=>{response.writeHead(503,{"Content-Type":"application/json"});response.end('{"detail":"isolated_fixture_unavailable"}');});
  request.pipe(forwarded);
}).listen(3419,"127.0.0.1");
