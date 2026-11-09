import { screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { FakeWebSocket } from "../acceptance/helpers";
import { castBody, ID, mount, sixStages } from "../acceptance/v2_helpers";

afterEach(() => {
  vi.unstubAllGlobals();
  FakeWebSocket.reset();
});

it("the Voices panel has exactly one call to action", async () => {
  mount(`/projects/${ID}`, { projectStage: "CAST_APPROVED", stages: sixStages(["approved", "approved", "needs_review"], 3) });
  const panel = await screen.findByTestId("stage-panel-voices");
  await waitFor(() => expect(panel.querySelectorAll(".btn-cta")).toHaveLength(1));
});

it("each Cast card has at most one call to action", async () => {
  mount(`/projects/${ID}`, { cast: castBody() });
  const card = await screen.findByTestId("cast-card");
  expect(card.querySelectorAll(".btn-cta").length).toBeLessThanOrEqual(1);
});
