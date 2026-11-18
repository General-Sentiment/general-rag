import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTypescript from "eslint-config-next/typescript";

export default defineConfig([
  ...nextVitals,
  ...nextTypescript,
  globalIgnores([
    "public/pdfjs/**",
    ".venv/**", ".next/**", ".desktop-build/**", "output/**", "tmp/**", "vendor/**",
    "src-tauri/gen/**", "src-tauri/resources/**", "src-tauri/target/**",
  ]),
]);
