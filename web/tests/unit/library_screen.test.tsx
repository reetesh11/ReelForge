import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";
import { FakeWebSocket, json, renderApp, stubFetch, type Route } from "../acceptance/helpers";

afterEach(() => {
  vi.unstubAllGlobals();
  FakeWebSocket.reset();
});

const rec = (over: Record<string, unknown>) => ({
  id: "L1",
  name: "Tamatar",
  aliases: ["Tom"],
  look_text: "round red tomato",
  created_at: "2026-11-01T10:00:00Z",
  tags: ["fruit"],
  voice_reference: "",
  ...over,
});

it("shows the empty state", async () => {
  stubFetch([(url) => (url.pathname === "/api/v1/library/characters" ? json([]) : undefined)]);
  renderApp("/library");
  expect(await screen.findByRole("heading", { name: "Library" })).toBeTruthy();
  expect(await screen.findByText("No characters in your library yet. Approve a cast to save characters here.")).toBeTruthy();
});

it("lists cards with aliases, tags and the variant parent", async () => {
  stubFetch([
    (url) =>
      url.pathname === "/api/v1/library/characters"
        ? json([rec({}), rec({ id: "L2", name: "Tamatar (variant)", parent_character_id: "L1" })])
        : undefined,
  ]);
  renderApp("/library");
  const card = await screen.findByLabelText("Library character: Tamatar");
  expect(card.textContent).toContain("Tom");
  expect(card.textContent).toContain("fruit");
  const variant = await screen.findByLabelText("Library character: Tamatar (variant)");
  expect(variant.textContent).toContain("Variant of Tamatar");
  expect(within(card).getByRole("link", { name: "Tamatar" }).getAttribute("href")).toBe("/library/L1");
});

it("saves name, aliases and tags with PATCH", async () => {
  const patch: Route = (url, init) =>
    url.pathname === "/api/v1/library/characters/L1" && init?.method === "PATCH" ? json(rec({ name: "Tom" })) : undefined;
  const fetchFn = stubFetch([
    patch,
    (url) => (url.pathname === "/api/v1/library/characters/L1" ? json(rec({})) : undefined),
  ]);
  renderApp("/library/L1");
  const user = userEvent.setup();
  const name = await screen.findByLabelText("Name");
  await user.clear(name);
  await user.type(name, "Tom");
  const tags = screen.getByLabelText("Tags");
  await user.clear(tags);
  await user.type(tags, "a, b");
  await user.click(screen.getByRole("button", { name: "Save" }));
  const patched = () =>
    fetchFn.mock.calls.map((c) => c[0]).filter((r): r is Request => r instanceof Request && r.method === "PATCH");
  await waitFor(() => expect(patched()).toHaveLength(1));
  expect(await patched()[0]?.clone().json()).toEqual({ name: "Tom", aliases: ["Tom"], tags: ["a", "b"] });
});
