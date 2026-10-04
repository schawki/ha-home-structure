// Bundles src/panel.ts into the one file Home Assistant loads (committed, because HACS does not run builds).
import { build } from "esbuild";

await build({
  entryPoints: ["src/panel.ts"], bundle: true, format: "esm", target: "es2022", minify: true,
  outfile: "../custom_components/home_structure/frontend/home-structure-panel.js", legalComments: "none", logLevel: "info",
  tsconfigRaw: { compilerOptions: { experimentalDecorators: true, useDefineForClassFields: false } },
});
