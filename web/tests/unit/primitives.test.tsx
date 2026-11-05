import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { ActionBar } from "@/components/ActionBar";
import { Chip } from "@/components/Chip";
import { IconButton } from "@/components/IconButton";
import { Notice } from "@/components/Notice";
import { StateMessage } from "@/components/StateMessage";

it("IconButton sets name, title and svg and fires onClick", () => {
  const onClick = vi.fn();
  render(<IconButton label="Regenerate 4 more" icon="regenerate" onClick={onClick} />);
  const b = screen.getByRole("button", { name: "Regenerate 4 more" });
  expect(b.getAttribute("title")).toBe("Regenerate 4 more");
  expect(b.classList.contains("btn-icon")).toBe(true);
  expect(b.querySelector("svg")).not.toBeNull();
  fireEvent.click(b);
  expect(onClick).toHaveBeenCalled();
});

it("IconButton danger tone adds btn-danger", () => {
  render(<IconButton label="Delete" icon="trash" tone="danger" />);
  expect(screen.getByRole("button", { name: "Delete" }).classList.contains("btn-danger")).toBe(true);
});

it("Notice, StateMessage, Chip and ActionBar render their classes", () => {
  render(
    <div>
      <Notice tone="success">Saved</Notice>
      <StateMessage>Loading...</StateMessage>
      <Chip tone="green" testId="c">Approved</Chip>
      <ActionBar left={<span>left</span>} cta={<button type="button">go</button>} />
    </div>,
  );
  expect(screen.getByText("Saved").closest(".notice")?.classList.contains("success")).toBe(true);
  expect(screen.getByText("Loading...").classList.contains("state-message")).toBe(true);
  expect(screen.getByTestId("c").classList.contains("chip-green")).toBe(true);
  expect(screen.getByTestId("action-bar").textContent).toContain("left");
});
