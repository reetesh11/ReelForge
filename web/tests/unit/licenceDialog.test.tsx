import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";
import { LicenceDialog } from "@/assembly/LicenceDialog";

it("shows an upload without a note and an unchanged model line", () => {
  render(
    <LicenceDialog
      warnings={[
        { cue_id: "f1", kind: "sfx", file_name: "gong.wav", licence: "" },
        { model: "flux", version: "r1", licence: "" },
      ]}
      onExport={() => {}}
      onCancel={() => {}}
    />,
  );
  expect(screen.getByText("gong.wav - Licence note not filled in")).toBeTruthy();
  expect(screen.getByText("flux r1 - Licence not filled in")).toBeTruthy();
});
