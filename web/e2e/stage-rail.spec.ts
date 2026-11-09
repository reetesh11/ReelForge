import { expect, test } from "@playwright/test";

const API = "http://127.0.0.1:7400";

for (const width of [1440, 900]) {
  test(`stage rail cells are equal and span the content at ${width}px`, async ({ page, request }) => {
    const project = await (await request.post(`${API}/api/v1/projects`, { data: { title: `Rail ${width}` } })).json();
    await page.setViewportSize({ width, height: 900 });
    await page.goto(`/projects/${project.id}`);

    const rail = page.locator('ol[aria-label="Stages"]');
    await expect(rail).toBeVisible();
    const cells = rail.locator("> li");
    await expect(cells).toHaveCount(6);

    const box = await rail.boundingBox();
    if (!box) throw new Error("rail has no box");
    const boxes: Array<{ x: number; y: number; width: number; height: number }> = [];
    for (let i = 0; i < 6; i++) {
      const b = await cells.nth(i).boundingBox();
      if (!b) throw new Error(`cell ${i} has no box`);
      boxes.push(b);
    }
    const at = (i: number) => {
      const b = boxes[i];
      if (!b) throw new Error(`no box ${i}`);
      return b;
    };
    const first = at(0);
    const last = at(5);
    for (const b of boxes) expect(Math.abs(b.width - first.width)).toBeLessThanOrEqual(1);
    for (let i = 1; i < 6; i++) {
      const gap = at(i).x - (at(i - 1).x + at(i - 1).width);
      expect(gap).toBeLessThanOrEqual(8);
    }
    expect(Math.abs(first.x - box.x)).toBeLessThanOrEqual(1);
    expect(Math.abs(last.x + last.width - (box.x + box.width))).toBeLessThanOrEqual(1);

    for (let i = 0; i < 6; i++) {
      const cell = cells.nth(i);
      const name = cell.getByTestId("stage-name");
      const state = cell.getByTestId("stage-state");
      await expect(name).toBeVisible();
      await expect(state).toBeVisible();
      const nb = await name.boundingBox();
      const sb = await state.boundingBox();
      if (!nb || !sb) throw new Error("missing box");
      expect(sb.y).toBeGreaterThanOrEqual(nb.y + nb.height - 1);
    }

    const keyFrames = cells.nth(3).getByTestId("stage-name");
    await expect(keyFrames).toContainText("Key frames");
    const lineHeight = await keyFrames.evaluate((el) => parseFloat(getComputedStyle(el).lineHeight) || 20);
    const kb = await keyFrames.boundingBox();
    if (!kb) throw new Error("missing box");
    expect(kb.height).toBeLessThanOrEqual(lineHeight * 1.5 + 8);
  });
}
