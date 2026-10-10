// Syntax-only fallback. This is NOT TypeScript type checking or a frontend build.
// Use npm run check after installing actual project dependencies.
const fs = require('node:fs');
const path = require('node:path');
const ts = require('typescript');
const root = path.resolve(__dirname, '..');
const files = [];
function visit(dir) {
  for (const item of fs.readdirSync(dir, {withFileTypes: true})) {
    const file = path.join(dir, item.name);
    if (item.isDirectory() && !['node_modules', 'dist'].includes(item.name)) visit(file);
    else if (item.isFile() && /\.tsx?$/.test(item.name) && !/\.d\.ts$/.test(item.name)) files.push(file);
  }
}
visit(path.join(root, 'apps/web'));
visit(path.join(root, 'tests/e2e'));
files.push(path.join(root, 'playwright.config.ts'));
let failures = 0;
for (const file of files) {
  const result = ts.transpileModule(fs.readFileSync(file, 'utf8'), {
    fileName: file, reportDiagnostics: true,
    compilerOptions: {target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext, jsx: ts.JsxEmit.ReactJSX}
  });
  for (const error of result.diagnostics || []) {
    if (error.category === ts.DiagnosticCategory.Error) {
      console.error(file, ts.flattenDiagnosticMessageText(error.messageText, '\n'));
      failures++;
    }
  }
}
console.log(`Syntax-only: ${files.length} TypeScript files, ${failures} errors. Dependencies, types and browser behavior NOT checked.`);
process.exitCode = failures ? 1 : 0;
