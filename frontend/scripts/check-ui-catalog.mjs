/** Bundled UI contract: namespace parity, params, plurals and actual call keys. */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import ts from "typescript";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const src = path.join(root, "src");
const errors = [], catalogs = new Map();
const locales = [path.join(src, "composition", "locales"), ...fs.readdirSync(path.join(src, "features")).map(name => path.join(src, "features", name, "locales"))];
const params = value => [...value.matchAll(/{{\s*([^},\s]+)(?:,[^}]*)?\s*}}/g)].map(m => m[1]).sort();
for (const dir of locales) {
  if (!fs.existsSync(dir)) continue;
  const ns = dir.includes(`${path.sep}composition${path.sep}`) ? "shell" : path.basename(path.dirname(dir));
  const ko = JSON.parse(fs.readFileSync(path.join(dir, "ko.json"), "utf8"));
  const en = JSON.parse(fs.readFileSync(path.join(dir, "en.json"), "utf8"));
  catalogs.set(ns, { ko, en });
  if (JSON.stringify(Object.keys(ko).sort()) !== JSON.stringify(Object.keys(en).sort())) errors.push(`${ns}: key parity`);
  for (const [key, value] of Object.entries(en)) {
    if (typeof value !== "string" || typeof ko[key] !== "string" || !value || !ko[key]) errors.push(`${ns}:${key}: nonempty string required`);
    else if (JSON.stringify(params(value)) !== JSON.stringify(params(ko[key]))) errors.push(`${ns}:${key}: interpolation parity`);
    const base = key.replace(/_(one|other)$/, "");
    if (base !== key && (!en[`${base}_one`] || !en[`${base}_other`] || !ko[`${base}_one`] || !ko[`${base}_other`])) errors.push(`${ns}:${key}: plural parity`);
    // K04 applies to authored UI resources. Persona/post/name data never enter
    // this scan. The logo's actual bird description is an explicit brand use.
    if (typeof ko[key] === "string" && /둥지|지저귐|대꾸|모이|쪽지|나무|앵무/.test(ko[key]) && !/노란 앵무.*Angmoo.*로고/.test(ko[key]))
      errors.push(`${ns}:${key}: legacy generic product terminology`);
  }
}
const files = [];
function walk(dir) { for (const item of fs.readdirSync(dir, {withFileTypes:true})) { const file=path.join(dir,item.name); if(item.isDirectory())walk(file);else if(/\.tsx?$/.test(file))files.push(file); } }
walk(path.join(src,"features")); walk(path.join(src,"composition"));
let checked=0;
for (const file of files) {
  if (file.includes(`${path.sep}locales${path.sep}`)) continue;
  const source=fs.readFileSync(file,"utf8"), ast=ts.createSourceFile(file,source,ts.ScriptTarget.Latest,true);
  const nsMatch=source.match(/use(?:UiText|Translation)\("([^"]+)"\)/);
  const ns=nsMatch?.[1] ?? (file.includes(`${path.sep}features${path.sep}`) ? file.slice(file.indexOf(`${path.sep}features${path.sep}`)+10).split(path.sep)[0] : "shell");
  const catalog=catalogs.get(ns);
  function check(key) { checked++; if(!catalog?.en[key]&&!catalogs.get("shell")?.en[key])errors.push(`${path.relative(root,file)}: missing ${ns}:${key}`); }
  function visit(node) {
    if(ts.isCallExpression(node)&&["uiText","t"].includes(node.expression.getText(ast))&&node.arguments[0]&&ts.isStringLiteralLike(node.arguments[0])) check(node.arguments[0].text);
    // Validation messages and typed local errors are translated by their
    // consumers. Audit these authored values even though the call is dynamic.
    if (ts.isStringLiteralLike(node) && ts.isPropertyAssignment(node.parent) && node.parent.initializer === node) {
      const property = node.parent.name.getText(ast);
      if ((file.endsWith(`${path.sep}api${path.sep}request.ts`) && property === "message")
        || (file.includes(`${path.sep}world-packages${path.sep}components${path.sep}`) && ["message", "context"].includes(property))) check(node.text);
      let declaration = node.parent;
      while (declaration && !ts.isVariableDeclaration(declaration)) declaration = declaration.parent;
      if (declaration && ["ERROR_MESSAGES", "FIELD_LABELS", "IMAGE_INPUT_MESSAGES"].includes(declaration.name.getText(ast))) check(node.text);
    }
    if (file.endsWith(`${path.sep}world-package-import-client.tsx`) && ts.isStringLiteralLike(node) && /[가-힣]/.test(node.text)) {
      let fn = node.parent;
      while (fn && !ts.isFunctionDeclaration(fn)) fn = fn.parent;
      if (fn?.name && ["trustLabel", "duplicateLabel"].includes(fn.name.text)) check(node.text);
    }
    const authoredDeclarations = file.endsWith(`${path.sep}agent-create-client.tsx`)
      ? ["STEPS", "PERSONA_FIELDS"] : file.endsWith(`${path.sep}character-profile-screen.tsx`)
      ? ["PROFILE_TABS"] : file.endsWith(`${path.sep}post-feed-parts.tsx`)
      ? ["FEED_CONTENT_FILTER_OPTIONS"] : file.endsWith(`${path.sep}creator-studio-dashboard.tsx`)
      ? ["GROUPS"] : file.endsWith(`${path.sep}world-character-social-profile-activity.tsx`)
      ? ["TABS"] : [];
    if (authoredDeclarations.length && ts.isStringLiteralLike(node) && /[가-힣]/.test(node.text)) {
      let declaration = node.parent;
      while (declaration && !ts.isVariableDeclaration(declaration)) declaration = declaration.parent;
      if (declaration && authoredDeclarations.includes(declaration.name.getText(ast))) check(node.text);
    }
    if (file.endsWith(`${path.sep}post-feed-parts.tsx`) && ts.isStringLiteralLike(node) && /[가-힣]/.test(node.text)) {
      let fn = node.parent;
      while (fn && !ts.isFunctionDeclaration(fn)) fn = fn.parent;
      if (fn?.name?.text === "feedContentFilterEmptyText") check(node.text);
    }
    if (file.endsWith(`${path.sep}world-character-social-profile-activity.tsx`) && ts.isStringLiteralLike(node) && /[가-힣]/.test(node.text)) {
      let fn = node.parent;
      while (fn && !ts.isFunctionDeclaration(fn)) fn = fn.parent;
      if (fn?.name?.text === "emptyTitle") check(node.text);
    }
    if (file.endsWith(`${path.sep}creator-studio-dashboard.tsx`) && ts.isStringLiteralLike(node) && /[가-힣]/.test(node.text)) {
      let fn = node.parent;
      while (fn && !ts.isFunctionDeclaration(fn)) fn = fn.parent;
      if (fn?.name?.text === "statusLabel") check(node.text);
    }
    // The activity helper and fixed app labels are explicit authored maps.
    if(["activity.ts", "device-home-presentation.ts", "character-recent-activity-presentation.ts", "character-dashboard-presentation.ts", "active-agent-summary.tsx", "local-device-navigation.tsx", "world-app-navigation.ts"].some(name => file.endsWith(`${path.sep}${name}`))&&ts.isStringLiteralLike(node)&&/[가-힣]/.test(node.text)&&(!ts.isCallExpression(node.parent))) check(node.text);
    ts.forEachChild(node,visit);
  }
  visit(ast);
}
const unique=[...new Set(errors)].sort();
if(unique.length) { process.stderr.write(unique.join("\n")+"\n"); process.exitCode=1; }
else process.stdout.write(`UI catalog passed: ${catalogs.size} namespaces, ${checked} source keys; key/params/plural parity.\n`);
