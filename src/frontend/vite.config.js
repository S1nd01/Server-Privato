import { readFile, writeFile } from "node:fs/promises";
import { resolve } from "node:path";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [
    {
      name: "homeserver-precache",
      async writeBundle(options, bundle) {
        const worker = resolve(options.dir, "sw.js");
        const assets = Object.keys(bundle).filter((name) =>
          name.startsWith("assets/"),
        );
        const source = await readFile(worker, "utf8");
        await writeFile(
          worker,
          source.replace(
            '"__BUILD_ASSETS__"',
            JSON.stringify(assets.map((name) => "/" + name)),
          ),
        );
      },
    },
  ],
});
