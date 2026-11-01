import { expect, test } from "@playwright/test";

const API = "http://127.0.0.1:7400";

test("project list and stage stepper render", async ({ page, request }) => {
  const created = await request.post(`${API}/api/v1/projects`, { data: { title: "E2E tomato" } });
  expect(created.status()).toBe(201);
  const project = await created.json();

  await page.goto("/projects");
  await expect(page.getByRole("heading", { name: "Projects" })).toBeVisible();
  const link = page.getByRole("link", { name: "E2E tomato" });
  await expect(link).toBeVisible();
  await expect(page.getByText("0/6 stages approved").first()).toBeVisible();

  await link.click();
  await expect(page).toHaveURL(new RegExp(`/projects/${project.id}`));
  const stages = page.getByRole("list", { name: "Stages" }).getByRole("listitem");
  await expect(stages).toHaveCount(6);
  await expect(page.getByText("This stage arrives in a later milestone.")).toBeVisible();
});

test("job progress reaches the UI over the websocket without polling jobs", async ({ page, request }) => {
  const project = await (await request.post(`${API}/api/v1/projects`, { data: { title: "E2E live" } })).json();
  const jobRequests: string[] = [];
  page.on("request", (r) => {
    if (new URL(r.url()).pathname.startsWith("/api/v1/jobs")) jobRequests.push(r.url());
  });

  await page.goto(`/projects/${project.id}`);
  await expect(page.getByRole("list", { name: "Stages" })).toBeVisible();
  await expect(page.getByText("Reconnecting...")).toBeHidden();

  const res = await request.post(`${API}/api/v1/projects/${project.id}/artifacts`, {
    data: {
      owner_type: "character",
      owner_id: "e2e",
      kind: "candidate",
      media: "image",
      prompt: "tomato",
      seed: 1,
      stage: "frames",
      params: { mock: { sleep_s: 6, steps: 12 } },
    },
  });
  expect(res.status()).toBe(202);

  const frames = page.getByRole("list", { name: "Stages" }).getByRole("listitem").nth(3);
  await expect(frames).toContainText(/Rendering \d+%/, { timeout: 20_000 });
  const first = Number(/Rendering (\d+)%/.exec((await frames.textContent()) ?? "")?.[1]);
  await expect
    .poll(async () => Number(/Rendering (\d+)%/.exec((await frames.textContent()) ?? "")?.[1] ?? 100), {
      timeout: 20_000,
    })
    .toBeGreaterThan(first);
  await expect(frames).not.toContainText("Rendering", { timeout: 30_000 });
  expect(jobRequests).toEqual([]);
});
