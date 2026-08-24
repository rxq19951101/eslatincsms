import * as fs from 'fs';
import * as path from 'path';
import * as ts from 'typescript';

import { en } from '../en';
import { es } from '../es';
import { zh } from '../zh';

function leafKeys(value: unknown, prefix = ''): string[] {
  if (!value || typeof value !== 'object') return [prefix];
  return Object.entries(value as Record<string, unknown>).flatMap(([key, child]) =>
    leafKeys(child, prefix ? `${prefix}.${key}` : key)
  );
}

const APP_ROOT = path.resolve(__dirname, '../../..');
const USER_COPY_ATTRIBUTES = new Set([
  'accessibilityHint',
  'accessibilityLabel',
  'description',
  'headerTitle',
  'label',
  'message',
  'placeholder',
  'subtitle',
  'title',
]);
const ALLOWED_LITERAL_COPY = new Set(['EsLatin', 'kW', 'kWh', '/kWh', 'COP / kWh']);

function sourceFiles(root: string): string[] {
  const result: string[] = [];
  for (const entry of fs.readdirSync(root, { withFileTypes: true })) {
    const fullPath = path.join(root, entry.name);
    if (entry.isDirectory()) {
      if (entry.name !== '__tests__' && fullPath !== path.join(APP_ROOT, 'src', 'i18n')) {
        result.push(...sourceFiles(fullPath));
      }
    } else if (entry.name.endsWith('.tsx')) {
      result.push(fullPath);
    }
  }
  return result;
}

function hardcodedUiCopy(filePath: string): string[] {
  const source = fs.readFileSync(filePath, 'utf8');
  const sourceFile = ts.createSourceFile(filePath, source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  const findings: string[] = [];
  const record = (node: ts.Node, value: string) => {
    const copy = value.trim();
    if (!copy || ALLOWED_LITERAL_COPY.has(copy) || !/[A-Za-z\u3400-\u9fff]/.test(copy)) return;
    const line = sourceFile.getLineAndCharacterOfPosition(node.getStart()).line + 1;
    findings.push(`${path.relative(APP_ROOT, filePath)}:${line}: ${JSON.stringify(copy)}`);
  };

  const visit = (node: ts.Node) => {
    if (ts.isJsxText(node)) record(node, node.text);
    if (
      ts.isJsxAttribute(node) &&
      ts.isIdentifier(node.name) &&
      USER_COPY_ATTRIBUTES.has(node.name.text) &&
      node.initializer &&
      ts.isStringLiteral(node.initializer)
    ) {
      record(node, node.initializer.text);
    }
    if (ts.isCallExpression(node)) {
      const expression = node.expression.getText(sourceFile);
      if (expression === 'Alert.alert' || expression === 'alert') {
        node.arguments.forEach((argument) => {
          if (ts.isStringLiteral(argument) || ts.isNoSubstitutionTemplateLiteral(argument)) {
            record(argument, argument.text);
          }
        });
      }
    }
    ts.forEachChild(node, visit);
  };
  visit(sourceFile);
  return findings;
}

describe('App i18n integrity', () => {
  it('keeps Spanish, English, and Chinese dictionary leaf keys identical', () => {
    const canonical = leafKeys(es).sort();
    expect(leafKeys(en).sort()).toEqual(canonical);
    expect(leafKeys(zh).sort()).toEqual(canonical);
  });

  it('rejects user-visible literals in JSX, common props, placeholders, labels, and alerts', () => {
    const files = [path.join(APP_ROOT, 'App.tsx'), ...sourceFiles(path.join(APP_ROOT, 'src'))];
    expect(files.flatMap(hardcodedUiCopy)).toEqual([]);
  });
});
