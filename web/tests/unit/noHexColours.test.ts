import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, resolve } from "node:path";
import { expect, it } from "vitest";

const SRC = resolve(__dirname, "../../src");
const walk = (dir: string): string[] =>
  readdirSync(dir).flatMap((n) => (statSync(join(dir, n)).isDirectory() ? walk(join(dir, n)) : [join(dir, n)]));

it("keeps raw colours in theme.css only", () => {
  const bad = walk(SRC)
    .filter((f) => /\.(tsx?|css)$/.test(f) && !/theme\.css$|schema\.d\.ts$/.test(f))
    .filter((f) => /#[0-9a-fA-F]{3,8}\b|rgba?\(/.test(readFileSync(f, "utf8")));
  expect(bad).toEqual([]);
});
