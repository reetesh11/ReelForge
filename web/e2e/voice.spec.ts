import { expect, test } from "@playwright/test";

const API = "http://127.0.0.1:7400";
const PNG_BASE64 =
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==";

const STORY = `version: 1
title: "E2E voices"
language: hindi
style: "3D cartoon"
aspect: "9:16"
fps: 24
target_seconds: 12
characters:
  tomato:
    name: "Tamatar"
    look: "round red tomato"
scenes:
  - id: s1
    speaker: tomato
    line: "Namaste doston aaj hum thekua banayenge"
    action: "Tamatar waves"
    duration: 6.0
  - id: s2
    speaker: tomato
    line: "Chalo shuru karte hain"
    action: "Tamatar smiles"
    duration: 6.0
`;

test("generate voice lines, approve them all and continue to key frames", async ({ page, request }) => {
  const project = await (await request.post(`${API}/api/v1/projects`, { data: { title: "E2E voices" } })).json();
  const base = `${API}/api/v1/projects/${project.id}`;
  expect(
    (await request.put(`${base}/story`, { data: STORY, headers: { "Content-Type": "text/plain" } })).status(),
  ).toBe(200);
  expect((await request.post(`${base}/story:approve`)).status()).toBe(200);

  await page.goto(`/projects/${project.id}`);
  const row = page.getByLabel("Cast", { exact: true }).getByLabel("Character: Tamatar");
  await row.getByLabel("Choose an image file").setInputFiles({
    name: "photo.png",
    mimeType: "image/png",
    buffer: Buffer.from(PNG_BASE64, "base64"),
  });
  await expect(row.locator("button.tile")).toHaveCount(1, { timeout: 20_000 });
  await row.locator("button.tile").first().click();
  await row.getByRole("button", { name: "Approve this one" }).click();
  await page.getByRole("button", { name: "Approve anyway" }).click();
  await expect(row.getByText("Approved", { exact: true })).toBeVisible();

  await row.getByText("Voice setup", { exact: true }).click();
  await row.getByLabel("Preset voice").selectOption("ravi");
  await page.getByRole("list", { name: "Stages" }).getByRole("link", { name: /Voices/ }).click();
  const board = page.getByLabel("Voices", { exact: true });
  await expect(board).toBeVisible();
  await expect(board.getByText("0 of 2 lines approved")).toBeVisible();

  await board.getByRole("button", { name: "Generate all lines" }).click();
  const scene1 = board.getByRole("group", { name: "Scene s1" });
  const scene2 = board.getByRole("group", { name: "Scene s2" });
  await expect(scene1.getByText("Ready", { exact: true })).toBeVisible({ timeout: 45_000 });
  await expect(scene2.getByText("Ready", { exact: true })).toBeVisible({ timeout: 45_000 });

  const next = board.getByRole("button", { name: "Continue to key frames" });
  await expect(next).toBeDisabled();
  await scene1.getByRole("button", { name: "Approve", exact: true }).click();
  await expect(scene1.getByText("Approved", { exact: true })).toBeVisible();
  await scene2.getByRole("button", { name: "Approve", exact: true }).click();
  await expect(board.getByText("2 of 2 lines approved")).toBeVisible();
  await expect(next).toBeEnabled();
});
