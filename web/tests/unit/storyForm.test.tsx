import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { FakeWebSocket } from "../acceptance/helpers";
import { ID, mount, sixStages } from "../acceptance/v2_helpers";

afterEach(() => {
  vi.unstubAllGlobals();
  FakeWebSocket.reset();
});

const DRAFT = { projectStage: "DRAFT", stages: sixStages(["needs_review"], 1), storyApproved: false };

it("shows a read-only settings summary that expands into the editable fields", async () => {
  mount(`/projects/${ID}`, DRAFT);
  await screen.findByLabelText("Scene s1");
  expect(screen.getByTestId("settings-summary").textContent).toContain("3D cartoon");
  expect(screen.queryByLabelText("Visual style")).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "Edit settings" }));
  expect(screen.getByLabelText("Visual style")).toBeTruthy();
});

it("asks before leaving the Story stage with unsaved changes", async () => {
  const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
  mount(`/projects/${ID}`, { ...DRAFT, stages: sixStages(["needs_review", "approved"], 2) });
  const scene = await screen.findByLabelText("Scene s2");
  fireEvent.change(within(scene).getByRole("textbox", { name: "Action" }), { target: { value: "Aloo dances" } });
  await waitFor(() => expect(screen.getByText("Unsaved changes")).toBeTruthy());
  fireEvent.click(await screen.findByRole("link", { name: /Cast/ }));
  expect(confirm).toHaveBeenCalledWith("You have unsaved changes. Leave anyway?");
  expect(screen.getByTestId("stage-panel-story")).toBeTruthy();
  confirm.mockRestore();
});
