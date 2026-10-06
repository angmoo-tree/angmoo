import fs from 'node:fs';
import path from 'node:path';
import ts from 'typescript';

const root = process.cwd();
const rows = [];
function visitDir(directory) {
  for (const item of fs.readdirSync(directory, { withFileTypes: true })) {
    const full = path.join(directory, item.name);
    if (item.isDirectory() && !/^(\.next|out|node_modules|locales|tests|test-results)$/.test(item.name)) visitDir(full);
    else if (/\.[jt]sx?$/.test(item.name) && !/ui-foundation|locales|test/.test(full)) {
      const source = ts.createSourceFile(full, fs.readFileSync(full, 'utf8'), ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
      function scan(node) {
        if ((ts.isJsxText(node) || ts.isStringLiteral(node) || ts.isNoSubstitutionTemplateLiteral(node)) && /[가-힣]/.test(node.text)) {
          let parent = node.parent;
          let component = null;
          let localized = false;
          let caller = null;
          while (parent) {
            if (ts.isCallExpression(parent) && ts.isIdentifier(parent.expression)) {
              caller ??= parent.expression.text;
              localized ||= /^(uiText|t)$/.test(parent.expression.text);
            }
            if (ts.isFunctionDeclaration(parent) && parent.name && /^[A-Z]|^use[A-Z]/.test(parent.name.text)) component ??= parent.name.text;
            if ((ts.isArrowFunction(parent) || ts.isFunctionExpression(parent)) && ts.isVariableDeclaration(parent.parent) && ts.isIdentifier(parent.parent.name) && /^[A-Z]|^use[A-Z]/.test(parent.parent.name.text)) component ??= parent.parent.name.text;
            parent = parent.parent;
          }
          rows.push({ file: path.relative(root, full).replaceAll('\\', '/'), line: source.getLineAndCharacterOfPosition(node.getStart()).line + 1,
            text: node.text.trim().replace(/\s+/g, ' '), kind: ts.SyntaxKind[node.kind], component, localized, caller });
        }
        ts.forEachChild(node, scan);
      }
      scan(source);
    }
  }
}
for (const directory of ['src/features', 'src/composition', 'src/components', 'src/lib', 'src/utils', 'static-shell']) visitDir(path.join(root, directory));
const target = path.resolve(root, '../artifacts/multilingual-gemini-20261003/ui-inventory.json');
fs.writeFileSync(target, JSON.stringify(rows, null, 2));
console.log(JSON.stringify({ rows: rows.length, unique: new Set(rows.map(row => row.text)).size, files: new Set(rows.map(row => row.file)).size,
  componentStrings: rows.filter(row => row.component).length }));
