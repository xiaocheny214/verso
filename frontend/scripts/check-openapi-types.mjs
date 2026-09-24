import { spawnSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const frontendRoot = dirname(dirname(fileURLToPath(import.meta.url)));
const specPath = join(frontendRoot, "../openapi/openapi.json");
const committedPath = join(frontendRoot, "src/lib/api/schema.d.ts");
const cli = join(frontendRoot, "node_modules/openapi-typescript/bin/cli.js");

const generated = spawnSync(process.execPath, [cli, specPath], {
  cwd: frontendRoot,
  encoding: "utf8",
});

if (generated.status !== 0) {
  process.stderr.write(
    generated.stderr || generated.stdout || "openapi-typescript failed\n",
  );
  process.exit(generated.status === null ? 1 : generated.status);
}

const normalize = (text) => text.replace(/\r\n/g, "\n");
if (
  normalize(generated.stdout) !== normalize(readFileSync(committedPath, "utf8"))
) {
  process.stderr.write(
    "OpenAPI TypeScript types are stale: src/lib/api/schema.d.ts\nRun `pnpm openapi:sync` in frontend/.\n",
  );
  process.exit(1);
}
