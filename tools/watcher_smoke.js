#!/usr/bin/env bun

import { mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";

if (process.argv.length !== 3) {
  console.error("usage: watcher_smoke.js <watcher.node>");
  process.exit(2);
}

const binding = require(resolve(process.argv[2]));
const directory = await mkdtemp(join(tmpdir(), "opencode-watcher-smoke-"));
const events = [];
const callback = (error, items) => {
  if (error) throw error;
  events.push(...items);
};

try {
  await binding.subscribe(directory, callback, {});
  await writeFile(join(directory, "created.txt"), "watcher smoke\n");
  const deadline = Date.now() + 5000;
  while (!events.some((item) => item.path.endsWith("/created.txt"))) {
    if (Date.now() >= deadline) {
      throw new Error(`watcher event timed out: ${JSON.stringify(events)}`);
    }
    await Bun.sleep(50);
  }
  await binding.unsubscribe(directory, callback, {});
  console.log(JSON.stringify({ result: "pass", events }));
} finally {
  await rm(directory, { recursive: true, force: true });
}
