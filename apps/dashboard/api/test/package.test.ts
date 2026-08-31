import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdtempSync, rmSync } from "node:fs";
import { createRequire } from "node:module";
import { tmpdir } from "node:os";
import { dirname, resolve } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const projectRoot = resolve(
  dirname(fileURLToPath(import.meta.url)),
  "../../../..",
);
const require = createRequire(import.meta.url);

test("packages a CommonJS Lambda entrypoint Node can require", () => {
  execFileSync("just", ["package-dashboard"], {
    cwd: projectRoot,
    stdio: "inherit",
  });

  const extractionDirectory = mkdtempSync(
    resolve(tmpdir(), "dashboard-package-"),
  );
  try {
    execFileSync(
      "unzip",
      ["-q", "dist/dashboard.zip", "-d", extractionDirectory],
      {
        cwd: projectRoot,
      },
    );
    const loaded = require(resolve(extractionDirectory, "index.js"));
    assert.equal(typeof loaded.handler, "function");
  } finally {
    rmSync(extractionDirectory, { force: true, recursive: true });
  }
});
