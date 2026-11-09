import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { expect, it } from "vitest";

const css = readFileSync(resolve(__dirname, "../../src/theme.css"), "utf8");
const names = (block: string) => [...block.matchAll(/(--[a-z0-9-]+)\s*:/g)].map((m) => m[1] as string).sort();

it("defines the same token names in the light and dark sets", () => {
  const darkStart = css.indexOf("@media (prefers-color-scheme: dark)");
  expect(darkStart).toBeGreaterThan(0);
  const rootEnd = css.indexOf("}", css.indexOf(":root"));
  const light = names(css.slice(css.indexOf(":root"), rootEnd));
  const dark = names(css.slice(darkStart, css.indexOf("* {", darkStart)));
  expect(dark).toEqual(light);
  expect(light).toContain("--cta-from");
});

it("keeps one reduced-motion block", () => {
  expect(css.match(/prefers-reduced-motion/g)).toHaveLength(1);
});
