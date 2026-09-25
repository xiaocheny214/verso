import { spawnSync } from "node:child_process";
import path from "node:path";

const ignored = new Set(["schema.d.ts"]);
const files = process.argv
  .slice(2)
  .filter((file) => !ignored.has(path.basename(file)));

if (files.length === 0) {
  process.exit(0);
}

const result = spawnSync("pnpm", ["exec", "oxfmt", "--check", ...files], {
  stdio: "inherit",
  shell: true,
});
process.exit(result.status ?? 1);
