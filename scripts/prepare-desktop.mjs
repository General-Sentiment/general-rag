import { execFileSync } from "node:child_process";
import { chmodSync, cpSync, existsSync, mkdirSync, rmSync } from "node:fs";
import { arch, platform } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const resources = join(root, "src-tauri", "resources");
const server = join(resources, "server");
const bin = join(resources, "bin");
const buildRoot = join(root, ".desktop-build");
const python = join(root, ".venv", "bin", "python");

if (platform() !== "darwin" || arch() !== "arm64") {
  throw new Error("The current desktop bundle is configured for Apple silicon macOS.");
}
if (!existsSync(python)) {
  throw new Error("Create .venv and install requirements-desktop.txt before building the desktop app.");
}

execFileSync("npm", ["run", "build"], { cwd: root, stdio: "inherit" });

rmSync(resources, { recursive: true, force: true });
rmSync(buildRoot, { recursive: true, force: true });
mkdirSync(server, { recursive: true });
mkdirSync(bin, { recursive: true });
mkdirSync(buildRoot, { recursive: true });

cpSync(join(root, ".next", "standalone"), server, { recursive: true });
cpSync(join(root, ".next", "static"), join(server, ".next", "static"), { recursive: true });
cpSync(join(root, "public"), join(server, "public"), { recursive: true });

const bundledNode = join(bin, "node");
cpSync(process.execPath, bundledNode);
chmodSync(bundledNode, 0o755);

execFileSync(python, [
  "-m", "PyInstaller",
  "--noconfirm",
  "--clean",
  "--onefile",
  "--name", "general-rag-renderer",
  "--distpath", bin,
  "--workpath", join(buildRoot, "pyinstaller"),
  "--specpath", buildRoot,
  "--add-data", `${join(root, "assets", "fonts")}:assets/fonts`,
  "--add-data", `${join(root, "public", "fonts")}:public/fonts`,
  "--add-data", `${join(root, "vendor", "pyphen")}:vendor/pyphen`,
  join(root, "markdown_columns.py"),
], { cwd: root, stdio: "inherit" });

chmodSync(join(bin, "general-rag-renderer"), 0o755);
console.log(`Desktop resources prepared in ${resources}`);
