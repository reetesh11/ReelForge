import { screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { FakeWebSocket } from "../acceptance/helpers";
import { ID, mount, sixStages } from "../acceptance/v2_helpers";

afterEach(() => {
  vi.unstubAllGlobals();
  FakeWebSocket.reset();
});

it("keeps the shown stage in the URL only when the user picks one", async () => {
  mount(`/projects/${ID}`, { stages: sixStages(["approved", "needs_review"], 2) });
  await screen.findByTestId("stage-panel-cast");
  expect(screen.getByTestId("probe-location").textContent).toBe(`/projects/${ID}`);
});

it("shows the progress readout only after stages load", async () => {
  mount(`/projects/${ID}`, { stages: sixStages(["approved", "approved"], 2) });
  await waitFor(() => expect(screen.getByText("2 of 6 stages approved")).toBeTruthy());
});
