#!/usr/bin/env node
// Fails if messages/en.json and messages/bn.json differ in keys, contain empty strings, or use
// different {placeholders} for the same key. Run in CI (`pnpm i18n:check`).
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const root = join(dirname(fileURLToPath(import.meta.url)), "..", "messages");
const load = (l) => JSON.parse(readFileSync(join(root, `${l}.json`), "utf8"));

function flatten(obj, prefix = "", out = {}) {
  for (const [k, v] of Object.entries(obj)) {
    const key = prefix ? `${prefix}.${k}` : k;
    if (v && typeof v === "object") flatten(v, key, out);
    else out[key] = v;
  }
  return out;
}

const placeholders = (s) => [...String(s).matchAll(/\{(\w+)\}/g)].map((m) => m[1]).sort().join(",");
const en = flatten(load("en"));
const bn = flatten(load("bn"));
const errors = [];

for (const k of Object.keys(en)) if (!(k in bn)) errors.push(`missing in bn.json: ${k}`);
for (const k of Object.keys(bn)) if (!(k in en)) errors.push(`missing in en.json: ${k}`);
for (const [name, cat] of [["en", en], ["bn", bn]]) {
  for (const [k, v] of Object.entries(cat)) {
    if (typeof v !== "string" || !v.trim()) errors.push(`empty or non-string in ${name}.json: ${k}`);
  }
}
for (const k of Object.keys(en)) {
  if (k in bn && placeholders(en[k]) !== placeholders(bn[k])) {
    errors.push(`placeholder mismatch for ${k}: en {${placeholders(en[k])}} vs bn {${placeholders(bn[k])}}`);
  }
}

if (errors.length) {
  console.error(errors.join("\n"));
  console.error(`\ni18n check failed: ${errors.length} problem(s)`);
  process.exit(1);
}
console.log(`i18n check passed: ${Object.keys(en).length} keys in en and bn`);
