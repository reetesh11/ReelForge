import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { FakeWebSocket } from "./helpers";
import { ID, mount, sixStages, YAML_TEXT } from "./v2_helpers";

afterEach(() => {
  vi.unstubAllGlobals();
  FakeWebSocket.reset();
});

const DRAFT = { projectStage: "DRAFT", stages: sixStages(["needs_review"], 1), storyApproved: false };
const yamlBox = () => screen.getByRole("textbox", { name: "YAML editor" }) as HTMLTextAreaElement;

describe("AC-10 story form sections and textareas", () => {
  it("renders labelled character and scene sections with full multi-line textareas", async () => {
    mount(`/projects/${ID}`, DRAFT);
    const character = await screen.findByLabelText("Character tomato");
    const look = within(character).getByRole("textbox", { name: "Look" }) as HTMLTextAreaElement;
    expect(look.tagName).toBe("TEXTAREA");
    expect(look.value).toBe("round red tomato\nwith a leaf hat");

    const scene = screen.getByLabelText("Scene s1");
    const action = within(scene).getByRole("textbox", { name: "Action" }) as HTMLTextAreaElement;
    const line = within(scene).getByRole("textbox", { name: "Line" }) as HTMLTextAreaElement;
    expect(action.tagName).toBe("TEXTAREA");
    expect(line.tagName).toBe("TEXTAREA");
    expect(action.value).toBe("Tamatar waves\nat the camera");
    expect(line.value).toBe("Namaste doston,\naaj kya banayein?");
    expect(screen.getByLabelText("Scene s2")).toBeTruthy();
  });

  it("editing a field still updates the YAML", async () => {
    mount(`/projects/${ID}`, DRAFT);
    const scene = await screen.findByLabelText("Scene s2");
    const action = within(scene).getByRole("textbox", { name: "Action" });
    fireEvent.change(action, { target: { value: "Aloo dances" } });
    await userEvent.setup().click(screen.getByRole("tab", { name: "YAML" }));
    await waitFor(() => expect(yamlBox().value).toContain("action: Aloo dances"));
    expect(yamlBox().value).not.toContain("Tamatar smiles");
  });
});

describe("AC-11 needs update only in card headers", () => {
  it("shows the chip in the header of stale character and scene cards only", async () => {
    mount(`/projects/${ID}?stage=story`, {
      projectStage: "STORY_APPROVED",
      stages: sixStages(["approved", "needs_review"], 2),
      storyApproved: true,
      stale: [
        { owner_type: "character", owner_id: "tomato" },
        { owner_type: "scene", owner_id: "s1" },
      ],
    });
    const character = await screen.findByLabelText("Character tomato");
    await waitFor(() => expect(within(character).getByText("needs update")).toBeTruthy());
    expect(within(character).getByText("needs update").closest(".card-header")).not.toBeNull();
    const s1 = screen.getByLabelText("Scene s1");
    expect(within(s1).getByText("needs update").closest(".card-header")).not.toBeNull();
    expect(within(screen.getByLabelText("Scene s2")).queryByText("needs update")).toBeNull();
    const all = screen.getAllByText("needs update");
    expect(all).toHaveLength(2);
    all.forEach((el) => expect(el.closest(".card-header")).not.toBeNull());
    expect(document.body.textContent?.match(/needs update/g)).toHaveLength(2);
  });
});

describe("AC-12 unsaved changes indicator", () => {
  it("shows Unsaved changes and a primary Save only while the draft differs", async () => {
    mount(`/projects/${ID}`, DRAFT);
    const scene = await screen.findByLabelText("Scene s2");
    const bar = await screen.findByTestId("action-bar");
    const save = () => within(bar).getByRole("button", { name: "Save" });
    expect(within(bar).queryByText("Unsaved changes")).toBeNull();
    expect(save().classList.contains("btn-primary")).toBe(false);
    expect(save().classList.contains("btn-secondary")).toBe(true);

    const action = within(scene).getByRole("textbox", { name: "Action" });
    fireEvent.change(action, { target: { value: "Aloo dances" } });
    await waitFor(() => expect(within(bar).getByText("Unsaved changes")).toBeTruthy());
    expect(save().classList.contains("btn-primary")).toBe(true);

    await userEvent.setup().click(screen.getByRole("tab", { name: "YAML" }));
    fireEvent.change(yamlBox(), { target: { value: YAML_TEXT } });
    await waitFor(() => expect(within(bar).queryByText("Unsaved changes")).toBeNull());
    expect(save().classList.contains("btn-primary")).toBe(false);
  });
});
