// A fresh LOCAL production-browser fixture, not an installer/deployment command.
// Windows Next standalone traces can contain file-typed directory symlinks.
// Keep those outputs intact and reuse the project's dependencies in a new root.
import {cpSync,copyFileSync,existsSync,mkdirSync,readdirSync,symlinkSync,writeFileSync} from "node:fs";
import {dirname,join,resolve,sep} from "node:path";
import {fileURLToPath} from "node:url";
const frontend=resolve(dirname(fileURLToPath(import.meta.url)),"..");
const repo=resolve(frontend,"..");
const dist=resolve(frontend,process.argv[2]??".next-comfy-security-final");
const destination=resolve(repo,process.argv[3]??"artifacts/comfy-security-20261012/next-runtime-final");
const allowed=join(repo,"artifacts","comfy-security-20261012");
if(!dist.startsWith(frontend+sep)||!destination.startsWith(allowed+sep)||existsSync(destination))throw new Error("fresh_owned_fixture_root_required");
const product=join(destination,"frontend"),output=join(product,dist.slice(frontend.length+1));
mkdirSync(output,{recursive:true});mkdirSync(join(destination,"docs"));
writeFileSync(join(destination,".synthetic-production-next"),"LOCAL compiled browser fixture; original project dependencies\n");
copyFileSync(join(dist,"standalone","frontend","server.js"),join(product,"server.js"));
for(const directory of ["server","static"])cpSync(join(dist,directory),join(output,directory),{recursive:true});
for(const file of readdirSync(dist,{withFileTypes:true}))if(file.isFile())copyFileSync(join(dist,file.name),join(output,file.name));
cpSync(join(frontend,"public"),join(product,"public"),{recursive:true});
for(const file of ["agent_guide.md","agent_guide.en.md"])copyFileSync(join(repo,"docs",file),join(destination,"docs",file));
symlinkSync(join(frontend,"node_modules"),join(product,"node_modules"),process.platform==="win32"?"junction":"dir");
console.log("Prepared LOCAL production Next fixture. This does not certify a packaged dependency payload.");
