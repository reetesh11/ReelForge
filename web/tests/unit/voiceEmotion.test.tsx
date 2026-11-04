import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import type { VoiceOut } from "@/api/voice";
import { VoiceSetup } from "@/voice/VoiceSetup";

const cloned: VoiceOut = {
  mode: "cloned",
  model: "omnivoice",
  voice_id: null,
  reference_text: "x",
  speed: 1,
  language: "hi",
  model_mismatch: false,
};

function setup(over: Partial<Parameters<typeof VoiceSetup>[0]> = {}) {
  const props = {
    name: "Tamatar",
    voice: cloned,
    presets: [],
    onSet: vi.fn(),
    onUpload: vi.fn(),
    onPreview: vi.fn(async () => "/media/sample"),
    onUploadEmotionClip: vi.fn(),
    ...over,
  };
  render(<VoiceSetup {...props} />);
  return props;
}

it("keeps Upload clip disabled until a file and a transcript are given", async () => {
  const props = setup();
  const button = screen.getAllByRole("button", { name: "Upload clip" })[0] as HTMLButtonElement;
  expect(button.disabled).toBe(true);
  await userEvent.type(screen.getByLabelText("Transcript for Happy"), "khush");
  expect(button.disabled).toBe(true);
  await userEvent.upload(
    screen.getByLabelText("Upload clip for Happy"),
    new File([new Uint8Array([1])], "h.wav", { type: "audio/wav" }),
  );
  expect(button.disabled).toBe(false);
  await userEvent.click(button);
  expect(props.onUploadEmotionClip).toHaveBeenCalledWith("happy", expect.any(File), "khush");
  expect((screen.getByLabelText("Transcript for Happy") as HTMLInputElement).value).toBe("");
});

it("shows no age line when the age props are not passed", () => {
  setup();
  expect(screen.queryByText("No age set")).toBeNull();
});

it("shows the age without a band when the band is unknown", () => {
  setup({ age: 30 });
  expect(screen.getByText("Age 30")).toBeTruthy();
});
