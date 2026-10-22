// Builds the widget's interactive-UI bundle and the matching system prompt:
//   out/clippy-ui.js        → served as /static/clippy-ui.js
//   out/openui_prompt.txt        → read by the backend for bots with generative UI
//   out/openui_prompt_leads.txt  → the same plus LeadForm, for bots with lead recipients
import * as esbuild from "esbuild";
import { mkdirSync, writeFileSync, statSync } from "node:fs";
import { gzipSync } from "node:zlib";
import { readFileSync } from "node:fs";

const common = {
  bundle: true,
  jsx: "automatic",
  loader: { ".css": "text" },
  define: { "process.env.NODE_ENV": '"production"' },
  legalComments: "none",
  logLevel: "warning",
};

mkdirSync("out", { recursive: true });

await esbuild.build({
  ...common,
  entryPoints: ["src/entry.tsx"],
  outfile: "out/clippy-ui.js",
  format: "iife",
  target: ["es2020"],
  minify: true,
});

await esbuild.build({
  ...common,
  entryPoints: ["src/prompt.tsx"],
  outfile: "out/prompt.mjs",
  format: "esm",
  platform: "node",
});
const { buildPrompts } = await import(new URL("./out/prompt.mjs", import.meta.url));
for (const [name, text] of Object.entries(buildPrompts())) writeFileSync(`out/${name}`, text);

const kb = (n) => `${(n / 1024).toFixed(0)} KB`;
const js = readFileSync("out/clippy-ui.js");
console.log(`clippy-ui.js: ${kb(statSync("out/clippy-ui.js").size)} (${kb(gzipSync(js).length)} gzip)`);
for (const name of ["openui_prompt.txt", "openui_prompt_leads.txt"]) console.log(`${name}: ${statSync(`out/${name}`).size} chars`);
