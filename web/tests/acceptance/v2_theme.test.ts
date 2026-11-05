import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, resolve } from "node:path";
import { describe, expect, it } from "vitest";

const SRC = resolve(__dirname, "../../src");
const CSS = readFileSync(join(SRC, "theme.css"), "utf8").replace(/\/\*[\s\S]*?\*\//g, "");

/** Index of the brace that closes the one opened at `open`. */
function closeOf(text: string, open: number): number {
  let depth = 0;
  for (let i = open; i < text.length; i++) {
    if (text[i] === "{") depth += 1;
    if (text[i] === "}") {
      depth -= 1;
      if (depth === 0) return i;
    }
  }
  throw new Error("unbalanced braces in theme.css");
}

type Block = { head: string; body: string };

function blocks(text: string): Block[] {
  const out: Block[] = [];
  let i = 0;
  while (i < text.length) {
    const open = text.indexOf("{", i);
    if (open < 0) break;
    const end = closeOf(text, open);
    out.push({ head: text.slice(i, open).trim(), body: text.slice(open + 1, end) });
    i = end + 1;
  }
  return out;
}

function decls(body: string): Record<string, string> {
  const out: Record<string, string> = {};
  for (const m of body.matchAll(/(--[a-z0-9-]+)\s*:\s*([^;]+);/gi)) out[m[1] as string] = (m[2] as string).trim();
  return out;
}

const top = blocks(CSS);
const light: Record<string, string> = {};
for (const b of top) if (b.head === ":root") Object.assign(light, decls(b.body));
const dark: Record<string, string> = {};
for (const m of top.filter((b) => /^@media\s*\(\s*prefers-color-scheme:\s*dark\s*\)$/.test(b.head))) {
  for (const inner of blocks(m.body)) if (inner.head === ":root") Object.assign(dark, decls(inner.body));
}

function lum(hex: string): number {
  const h = hex.replace("#", "");
  const [r, g, b] = [0, 2, 4].map((i) => {
    const c = parseInt(h.slice(i, i + 2), 16) / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  }) as [number, number, number];
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}
function ratio(a: string, b: string): number {
  const [x, y] = [lum(a), lum(b)];
  return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05);
}

const REQUIRED = [
  "--bg", "--surface", "--surface-2", "--border", "--text", "--muted", "--accent", "--focus", "--cta-from", "--cta-to",
  "--cta-text", "--green", "--amber", "--red", "--blue",
  ...["green", "amber", "red", "blue", "grey"].flatMap((c) => [`--chip-${c}-bg`, `--chip-${c}-fg`]),
  "--radius-card", "--fs-12", "--fs-14", "--fs-16", "--fs-20", "--fs-28", "--shadow-bar",
];

describe("AC-17 token sets and contrast", () => {
  it("light and dark define exactly the same tokens, including the required ones", () => {
    expect(Object.keys(light).length).toBeGreaterThan(0);
    expect(Object.keys(dark).length).toBeGreaterThan(0);
    expect(Object.keys(light).sort()).toEqual(Object.keys(dark).sort());
    for (const name of REQUIRED) expect(Object.keys(light), name).toContain(name);
    expect(light["--radius-card"]).toBe("12px");
  });

  for (const [name, set] of [["light", light], ["dark", dark]] as const) {
    describe(name, () => {
      const hex = (k: string) => {
        const v = set[k];
        expect(v, k).toMatch(/^#[0-9a-fA-F]{6}$/);
        return v as string;
      };

      it("text on bg and surface is at least 4.5:1", () => {
        expect(ratio(hex("--text"), hex("--bg"))).toBeGreaterThanOrEqual(4.5);
        expect(ratio(hex("--text"), hex("--surface"))).toBeGreaterThanOrEqual(4.5);
      });

      it("CTA label on both gradient stops is at least 4.5:1", () => {
        expect(ratio(hex("--cta-text"), hex("--cta-from"))).toBeGreaterThanOrEqual(4.5);
        expect(ratio(hex("--cta-text"), hex("--cta-to"))).toBeGreaterThanOrEqual(4.5);
      });

      it("chip text on its background is at least 4.5:1", () => {
        for (const c of ["green", "amber", "red", "blue", "grey"]) {
          expect(ratio(hex(`--chip-${c}-fg`), hex(`--chip-${c}-bg`)), c).toBeGreaterThanOrEqual(4.5);
        }
      });

      it("border and focus ring against the surface are at least 3:1", () => {
        expect(ratio(hex("--border"), hex("--surface"))).toBeGreaterThanOrEqual(3);
        expect(ratio(hex("--focus"), hex("--surface"))).toBeGreaterThanOrEqual(3);
      });
    });
  }
});

function walk(dir: string): string[] {
  return readdirSync(dir).flatMap((n) => {
    const p = join(dir, n);
    return statSync(p).isDirectory() ? walk(p) : [p];
  });
}

describe("AC-16 no raw colours outside the token file", () => {
  it("has no hex colour or rgb( in any other file under web/src", () => {
    const hex = /#(?:[0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b/;
    const offenders = walk(SRC)
      .filter((f) => !f.endsWith("theme.css") && !f.endsWith("schema.d.ts"))
      .filter((f) => /\.(tsx?|css|html)$/.test(f))
      .filter((f) => {
        const text = readFileSync(f, "utf8");
        return hex.test(text) || /rgba?\(/.test(text);
      })
      .map((f) => f.slice(SRC.length + 1));
    expect(offenders).toEqual([]);
  });
});

describe("AC-18 reduced motion", () => {
  const motion = top.filter((b) => /^@media\s*\(\s*prefers-reduced-motion:\s*reduce\s*\)$/.test(b.head));

  it("has one reduced-motion block that turns off animation and transition except on .spinner", () => {
    expect(motion).toHaveLength(1);
    const inner = blocks((motion[0] as Block).body);
    const off = inner.filter((b) => /animation:\s*none/.test(b.body) && /transition:\s*none/.test(b.body));
    expect(off.length).toBeGreaterThan(0);
    expect(off.some((b) => /\*/.test(b.head) && /:not\(\s*\.spinner\s*\)/.test(b.head))).toBe(true);
  });

  it("only spin, pulse, shimmer and slide keyframes exist and .spinner uses spin", () => {
    const names = [...CSS.matchAll(/@keyframes\s+([\w-]+)/g)].map((m) => m[1] as string);
    expect(names).toContain("spin");
    for (const n of names) expect(["spin", "pulse", "shimmer", "slide"]).toContain(n);
    expect(CSS).toMatch(/\.spinner[^{]*\{[^}]*animation:[^;}]*\bspin\b/);
  });
});
