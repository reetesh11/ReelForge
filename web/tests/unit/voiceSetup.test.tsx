import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import type { VoiceOut } from "@/api/voice";
import { VoiceSetup } from "@/voice/VoiceSetup";

const PRESETS = [
  { id: "asha", label: "Asha (female)" },
  { id: "ravi", label: "Ravi (male)" },
];

function voice(over: Partial<VoiceOut> = {}): VoiceOut {
  return {
    mode: "preset",
    model: "omnivoice",
    voice_id: null,
    reference_text: "",
    speed: 1,
    language: "hi",
    model_mismatch: false,
    ...over,
  };
}

function setup(v: VoiceOut | null, over: Partial<Parameters<typeof VoiceSetup>[0]> = {}) {
  const props = {
    name: "Tamatar",
    voice: v,
    presets: PRESETS,
    onSet: vi.fn(),
    onUpload: vi.fn(),
    onPreview: vi.fn(async () => "/media/sample"),
    ...over,
  };
  render(<VoiceSetup {...props} />);
  return props;
}

it("offers the three modes and sets a preset", async () => {
  const props = setup(null);
  expect(screen.getByLabelText("Preset")).toBeTruthy();
  expect(screen.getByLabelText("Cloned")).toBeTruthy();
  expect(screen.getByLabelText("Recorded lines")).toBeTruthy();
  await userEvent.selectOptions(screen.getByLabelText("Preset voice"), "ravi");
  expect(props.onSet).toHaveBeenCalledWith({ mode: "preset", voice_id: "ravi" });
});

it("previews the picked preset", async () => {
  const props = setup(voice({ voice_id: "asha" }));
  await userEvent.click(screen.getByRole("button", { name: "Preview" }));
  await waitFor(() => expect(props.onPreview).toHaveBeenCalledWith("asha"));
  expect(await screen.findByLabelText("Voice preview")).toBeTruthy();
});

it("cloned mode shows the hint, the clip note and saves the transcript", async () => {
  const props = setup(voice({ mode: "cloned", clip_seconds: 3.2, reference_text: "" }));
  expect(screen.getByText("Use a clean 5 to 10 second clip.")).toBeTruthy();
  expect(screen.getByText("Clips of 5 to 10 seconds clone best.")).toBeTruthy();
  expect(screen.getByLabelText("Upload reference clip")).toBeTruthy();
  await userEvent.type(screen.getByLabelText("What is said in the clip"), "namaste");
  await userEvent.click(screen.getByRole("button", { name: "Use this clip" }));
  expect(props.onSet).toHaveBeenCalledWith({ mode: "cloned", reference_text: "namaste" });
});

it("no clip-length note for a clip of 5 to 10 seconds", () => {
  setup(voice({ mode: "cloned", clip_seconds: 7 }));
  expect(screen.queryByText("Clips of 5 to 10 seconds clone best.")).toBeNull();
});

it("shows the model mismatch note", () => {
  setup(voice({ model: "omnivoice", model_mismatch: true, voice_id: "asha" }));
  expect(screen.getByText("Voice made with OmniVoice.")).toBeTruthy();
});

it("choosing recorded lines saves that mode", async () => {
  const props = setup(null);
  await userEvent.click(screen.getByLabelText("Recorded lines"));
  expect(props.onSet).toHaveBeenCalledWith({ mode: "recorded" });
});
