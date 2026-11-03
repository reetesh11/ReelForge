import { expect, test } from "@playwright/test";

const API = "http://127.0.0.1:7400";
const PNG_BASE64 =
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==";

const STORY = `version: 1
title: "E2E tale"
language: english
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
    action: "Tamatar waves"
    duration: 3.0
  - id: s2
    action: "Tamatar smiles"
    duration: 3.0
  - id: s3
    action: "Tamatar jumps"
    duration: 3.0
  - id: s4
    action: "Tamatar bows"
    duration: 3.0
`;

test("add an image, approve it, then find the character in the library", async ({ page, request }) => {
  const project = await (await request.post(`${API}/api/v1/projects`, { data: { title: "E2E cast" } })).json();
  const put = await request.put(`${API}/api/v1/projects/${project.id}/story`, {
    data: STORY,
    headers: { "Content-Type": "text/plain" },
  });
  expect(put.status()).toBe(200);
  expect((await request.post(`${API}/api/v1/projects/${project.id}/story:approve`)).status()).toBe(200);

  await page.goto(`/projects/${project.id}`);
  const cast = page.getByLabel("Cast", { exact: true });
  await expect(cast).toBeVisible();
  const row = cast.getByLabel("Character: Tamatar");
  // Uploading needs no GPU memory lease, so the flow also runs on a machine with little free
  // memory. Generating four candidates is covered by the backend tests and docs/manual-checks.md.
  await row.getByLabel("Upload my own image").setInputFiles({
    name: "my photo.png",
    mimeType: "image/png",
    buffer: Buffer.from(PNG_BASE64, "base64"),
  });
  await expect(row.getByRole("radio")).toHaveCount(1, { timeout: 20_000 });

  await row.getByRole("radio").first().click();
  await row.getByRole("button", { name: "Approve this one" }).click();
  await page.getByRole("button", { name: "Approve anyway" }).click();
  await expect(row.getByText("Approved", { exact: true })).toBeVisible();
  await expect(cast.getByText("1 of 1 characters approved")).toBeVisible();
  const stages = page.getByRole("list", { name: "Stages" }).getByRole("listitem");
  await expect(stages.nth(1)).toContainText("Approved");

  await page.getByRole("link", { name: "Library" }).click();
  await expect(page.getByRole("heading", { name: "Library" })).toBeVisible();
  await expect(page.getByLabel("Library character: Tamatar").first()).toBeVisible();
});
