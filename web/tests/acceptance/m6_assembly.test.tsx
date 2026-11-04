import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ComponentProps } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AssemblyScreen } from "@/assembly/AssemblyScreen";
import { Player } from "@/player/Player";
import { ShotBoard } from "@/shots/ShotBoard";
import { json, stubFetch } from "./helpers";

const ID = "01ARZ3NDEKTSV4RRFFQ69G5FAV";
const API = `/api/v1/projects/${ID}`;

afterEach(() => vi.unstubAllGlobals());

// ---- Player ------------------------------------------------------------------------

let time = 0;
let playing = 0;
let paused = 0;

beforeEach(() => {
  time = 0;
  playing = 0;
  paused = 0;
  Object.defineProperty(HTMLMediaElement.prototype, "currentTime", {
    configurable: true,
    get: () => time,
    set: (v: number) => {
      time = v;
    },
  });
  Object.defineProperty(HTMLMediaElement.prototype, "play", {
    configurable: true,
    value: () => {
      playing += 1;
      return Promise.resolve();
    },
  });
  Object.defineProperty(HTMLMediaElement.prototype, "pause", {
    configurable: true,
    value: () => {
      paused += 1;
    },
  });
});

function player(props: Partial<ComponentProps<typeof Player>> = {}) {
  return render(<Player src="/media/abc" label="Reel" {...props} />);
}

describe("Player", () => {
  it("labels the video and offers every control by name", () => {
    player();
    expect(screen.getByLabelText("Reel")).toBeTruthy();
    for (const name of ["Play", "Previous frame", "Next frame", "Loop", "Mute", "Safe-zone overlay"]) {
      expect(screen.getByRole("button", { name })).toBeTruthy();
    }
    expect(screen.getByRole("combobox", { name: "Speed" })).toBeTruthy();
    expect(screen.getByRole("slider", { name: "Scrub" })).toBeTruthy();
    const speeds = within(screen.getByRole("combobox", { name: "Speed" })).getAllByRole("option");
    expect(speeds.map((o) => o.textContent)).toEqual(["0.5x", "1x", "1.5x", "2x"]);
  });

  it("plays, and steps by exactly one frame while pausing", async () => {
    player();
    await userEvent.click(screen.getByRole("button", { name: "Play" }));
    expect(playing).toBe(1);
    time = 1;
    await userEvent.click(screen.getByRole("button", { name: "Next frame" }));
    expect(time).toBeCloseTo(1 + 1 / 24, 6);
    expect(paused).toBeGreaterThan(0);
    await userEvent.click(screen.getByRole("button", { name: "Previous frame" }));
    expect(time).toBeCloseTo(1, 6);
  });

  it("steps frames with the arrow keys on the focused group", () => {
    player();
    const group = screen.getByRole("group", { name: "Reel player" });
    time = 2;
    fireEvent.keyDown(group, { key: "ArrowRight" });
    expect(time).toBeCloseTo(2 + 1 / 24, 6);
    fireEvent.keyDown(group, { key: "ArrowLeft" });
    expect(time).toBeCloseTo(2, 6);
  });

  it("toggles loop and the safe-zone overlay, which is off by default", async () => {
    player();
    const loop = screen.getByRole("button", { name: "Loop" });
    expect(loop.getAttribute("aria-pressed")).toBe("false");
    await userEvent.click(loop);
    expect(loop.getAttribute("aria-pressed")).toBe("true");
    expect(screen.queryByTestId("safe-zone-overlay")).toBeNull();
    const zone = screen.getByRole("button", { name: "Safe-zone overlay" });
    expect(zone.getAttribute("aria-pressed")).toBe("false");
    await userEvent.click(zone);
    expect(zone.getAttribute("aria-pressed")).toBe("true");
    expect(screen.getByTestId("safe-zone-overlay")).toBeTruthy();
  });

  it("shows a loading note, then a retry on error", async () => {
    player();
    expect(screen.getByText("Loading video...")).toBeTruthy();
    const video = screen.getByLabelText("Reel");
    fireEvent.loadedData(video);
    expect(screen.queryByText("Loading video...")).toBeNull();
    fireEvent.error(video);
    expect(screen.getByText("Couldn't load this video.")).toBeTruthy();
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(screen.queryByText("Couldn't load this video.")).toBeNull();
  });
});

// ---- Assembly screen -------------------------------------------------------------------

type Over = Record<string, unknown>;

function edlOf(): Over {
  const shot = (id: string, n: number) => ({
    scene_id: id,
    artifact: `art${n}`,
    source_duration_s: 3,
    in_s: 0,
    out_s: 3,
    transition_in_s: 0,
  });
  return {
    version: 1,
    fps: 24,
    width: 1080,
    height: 1920,
    project_id: ID,
    video: [shot("s1", 1), shot("s2", 2)],
    dialogue: [
      { scene_id: "s1", artifact: "v1", offset_s: 0, duration_s: 2, gain_db: 0 },
      { scene_id: "s2", artifact: "v2", offset_s: 3, duration_s: 2, gain_db: 0 },
    ],
    captions: [
      { scene_id: "s1", speaker: "Tamatar", line_no: 1, text: "Arre Aloo", start_s: 0, end_s: 2, style: null },
      { scene_id: "s2", speaker: "Aloo", line_no: 2, text: "", start_s: 3, end_s: 5, style: null },
    ],
    caption_style: "auto",
    music: { tracks: [], duck: false },
    end_card: { enabled: false, duration_s: 1.5, template: "default" },
  };
}

function asm(over: Over = {}, preview: Over = {}, exp: Over = {}): Over {
  return {
    stage: "SHOTS_APPROVED",
    blocked_reason: null,
    edl: edlOf(),
    edl_hash: "h1",
    shots: [
      { scene_id: "s1", takes: [{ id: "t1", take_no: 1, active: true, video_url: "/media/t1" }] },
      {
        scene_id: "s2",
        takes: [
          { id: "t2", take_no: 1, active: true, video_url: "/media/t2" },
          { id: "t3", take_no: 2, active: false, video_url: "/media/t3" },
        ],
      },
    ],
    caption_status: { s1: "words", s2: "words" },
    preview: {
      state: "up_to_date", step: null, progress: null, url: "/media/p1", job_id: null, error: null,
      rebuild_in_s: null, ...preview,
    },
    export: {
      state: "idle", step: null, step_index: null, step_total: null, progress: null, job_id: null,
      failed_step: null, error: null, ...exp,
    },
    versions: [
      { version: 1, label: "Reel v1", reel_url: "/media/r1", cover_url: "/media/c1", created_at: "x", missing: false },
      { version: 2, label: "Reel v2", reel_url: "/media/r2", cover_url: "/media/c2", created_at: "x", missing: true },
    ],
    licence_warnings: [],
    caption_presets: [
      { id: "bold_pop", label: "Bold pop" },
      { id: "clean_subtitle", label: "Clean subtitle" },
      { id: "hindi_devanagari", label: "Hindi Devanagari" },
    ],
    ...over,
  };
}

function screenWith(state: Over, onBack = () => {}) {
  const posts: Array<{ path: string; body: Record<string, unknown> }> = [];
  stubFetch([
    async (url, init) => {
      if (url.pathname === `${API}/assembly` && init?.method === "GET") return json(state);
      if (init?.method === "POST") {
        const raw = typeof init.body === "string" ? init.body : "";
        posts.push({ path: url.pathname, body: raw ? (JSON.parse(raw) as Record<string, unknown>) : {} });
        if (url.pathname.endsWith(":edit")) return json({ assembly: state, notes: [] });
        if (url.pathname.endsWith(":export")) return json({ id: "j1", type: "assemble_final" }, 202);
        return json(state);
      }
      return undefined;
    },
  ]);
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <AssemblyScreen projectId={ID} onBack={onBack} />
    </QueryClientProvider>,
  );
  return posts;
}

describe("AssemblyScreen", () => {
  it("goes back to Shots", async () => {
    const back = vi.fn();
    screenWith(asm(), back);
    await userEvent.click(await screen.findByRole("button", { name: "Back to Shots" }));
    expect(back).toHaveBeenCalled();
  });

  it("lists the working copy and each version, flagging missing files", async () => {
    screenWith(asm());
    const sel = await screen.findByRole("combobox", { name: "Version" });
    expect(within(sel).getAllByRole("option").map((o) => o.textContent)).toEqual([
      "Editing: working copy", "Reel v1", "Reel v2",
    ]);
  });

  it.each([
    [{ state: "up_to_date" }, "Preview up to date"],
    [{ state: "out_of_date", rebuild_in_s: 1 }, "Out of date - rebuilding in 1 s"],
    [{ state: "pending", rebuild_in_s: 1 }, "Out of date - rebuilding in 1 s"],
    [{ state: "rebuilding", step: "Joining video", progress: 25 }, "Rebuilding preview: Joining video (25%)"],
    [{ state: "failed", error: "boom" }, "Preview failed - Retry"],
  ])("shows the preview badge for %j", async (preview, text) => {
    screenWith(asm({}, preview));
    expect(await screen.findByText(text)).toBeTruthy();
    expect(screen.getByRole("button", { name: "Rebuild preview" })).toBeTruthy();
  });

  it("offers timeline controls for each shot and dialogue clip", async () => {
    screenWith(asm());
    await screen.findByRole("combobox", { name: "Version" });
    for (const sid of ["s1", "s2"]) {
      for (const name of [
        `Move ${sid} earlier`, `Move ${sid} later`, `Nudge ${sid} dialogue earlier`, `Nudge ${sid} dialogue later`,
      ]) {
        expect(screen.getByRole("button", { name })).toBeTruthy();
      }
      for (const name of [
        `Trim in for ${sid}`, `Trim out for ${sid}`, `Dialogue offset for ${sid}`, `Crossfade into ${sid}`,
      ]) {
        expect(screen.getByRole("spinbutton", { name })).toBeTruthy();
      }
      expect(screen.getByRole("combobox", { name: `Take for ${sid}` })).toBeTruthy();
    }
  });

  it("sends timeline edits as operations", async () => {
    const posts = screenWith(asm());
    await userEvent.click(await screen.findByRole("button", { name: "Move s1 later" }));
    await waitFor(() => expect(posts.some((p) => p.path === `${API}/assembly:edit`)).toBe(true));
    expect(posts.at(-1)?.body).toMatchObject({ op: "reorder", scene_ids: ["s2", "s1"] });
    await userEvent.click(screen.getByRole("button", { name: "Nudge s2 dialogue later" }));
    await waitFor(() => expect(posts.some((p) => p.body.op === "nudge_dialogue")).toBe(true));
    const nudge = posts.find((p) => p.body.op === "nudge_dialogue");
    expect(nudge?.body.scene_id).toBe("s2");
    expect(nudge?.body.offset_s as number).toBeCloseTo(3 + 1 / 24, 4);
  });

  it("saves a caption line on blur and changes the style", async () => {
    const posts = screenWith(asm());
    const line = await screen.findByRole("textbox", { name: "Caption for Tamatar line 1" });
    expect((line as HTMLInputElement).value).toBe("Arre Aloo");
    expect(screen.getByRole("textbox", { name: "Caption for Aloo line 2" }).getAttribute("placeholder")).toBe(
      "No caption for this line",
    );
    await userEvent.clear(line);
    await userEvent.type(line, "Naya");
    fireEvent.blur(line);
    await waitFor(() => expect(posts.some((p) => p.body.op === "set_caption_text")).toBe(true));
    expect(posts.find((p) => p.body.op === "set_caption_text")?.body).toMatchObject({ scene_id: "s1", text: "Naya" });
    const style = screen.getByRole("combobox", { name: "Caption style" });
    expect(within(style).getAllByRole("option").map((o) => o.textContent)).toEqual(
      expect.arrayContaining(["Bold pop", "Clean subtitle", "Hindi Devanagari", "Auto"]),
    );
    await userEvent.selectOptions(style, "Clean subtitle");
    await waitFor(() => expect(posts.some((p) => p.body.op === "set_caption_style")).toBe(true));
    expect(posts.find((p) => p.body.op === "set_caption_style")?.body.style).toBe("clean_subtitle");
  });

  it("exports straight away when there is no licence warning", async () => {
    const posts = screenWith(asm());
    await userEvent.click(await screen.findByRole("button", { name: "Export final" }));
    await waitFor(() => expect(posts.some((p) => p.path === `${API}/assembly:export`)).toBe(true));
    expect(posts.at(-1)?.body).toEqual({ accept_licence_warning: false });
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("asks before exporting a reel with licence warnings", async () => {
    const warnings = [
      { model: "flux-x", version: "r1", licence: "Non-Commercial License" },
      { model: "vid-y", version: "r2", licence: "" },
    ];
    const posts = screenWith(asm({ licence_warnings: warnings }));
    await userEvent.click(await screen.findByRole("button", { name: "Export final" }));
    const dlg = await screen.findByRole("dialog", { name: "Licence check before export" });
    expect(within(dlg).getByText("flux-x r1 - Non-Commercial License")).toBeTruthy();
    expect(within(dlg).getByText("vid-y r2 - Licence not filled in")).toBeTruthy();
    expect(
      within(dlg).getByText(
        "Some models used in this reel are non-commercial or have no licence recorded. Exporting is allowed, but check you may publish this reel.",
      ),
    ).toBeTruthy();
    await userEvent.click(within(dlg).getByRole("button", { name: "Cancel" }));
    expect(posts.filter((p) => p.path.endsWith(":export"))).toEqual([]);
    await userEvent.click(screen.getByRole("button", { name: "Export final" }));
    await userEvent.click(await screen.findByRole("button", { name: "Export anyway" }));
    await waitFor(() => expect(posts.some((p) => p.path.endsWith(":export"))).toBe(true));
    expect(posts.at(-1)?.body).toEqual({ accept_licence_warning: true });
  });

  it("disables export while rebuilding, exporting or blocked", async () => {
    screenWith(asm({}, { state: "rebuilding", step: "Joining video", progress: 10 }));
    const btn = await screen.findByRole("button", { name: "Export final" });
    expect((btn as HTMLButtonElement).disabled).toBe(true);
  });

  it("shows the blocked reason and disables export", async () => {
    screenWith(asm({ blocked_reason: "Approve all shots before exporting." }));
    expect(await screen.findByText("Approve all shots before exporting.")).toBeTruthy();
    expect((screen.getByRole("button", { name: "Export final" }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("reports export progress, success and failure", async () => {
    screenWith(
      asm({}, {}, { state: "running", step: "Verifying", step_index: 9, step_total: 10, progress: 80, job_id: "j" }),
    );
    expect(await screen.findByText("Exporting: Verifying (9 of 10)")).toBeTruthy();
    expect((screen.getByRole("button", { name: "Export final" }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("names the failed step and offers a retry", async () => {
    screenWith(asm({}, {}, { state: "failed", failed_step: "Encoding", error: "ffmpeg died" }));
    expect(await screen.findByText("Export failed at Encoding. ffmpeg died")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Retry" })).toBeTruthy();
  });

  it("says when word timing is unavailable or still being worked out", async () => {
    screenWith(asm({ caption_status: { s1: "line", s2: "pending" } }, { state: "rebuilding", step: "Burning captions", progress: 70 }));
    expect(await screen.findByText("Word timing unavailable - showing the whole line")).toBeTruthy();
    expect(screen.getByText("Aligning captions...")).toBeTruthy();
  });
});

describe("ShotBoard hand-off", () => {
  it("continues to Assembly once every shot is approved", async () => {
    const take = {
      id: "t1", take_no: 1, seed: 1, active: true, approved: true, stale: false, source: "render",
      quality: "draft", video_url: "/media/t1", last_frame_id: "l1", inputs: [],
    };
    const shot = {
      scene_id: "s1", position: 1, shot_type: "talking", shot_type_auto: "talking", quality: "draft",
      width: 320, height: 576, frames: 81, shot_length_s: 3.375, motion_prompt: "x", state: "approved",
      blockers: [], frame_url: "/media/f1", takes: [take], job: null,
    };
    const board = {
      stage: "SHOTS_APPROVED", engine: { ok: true, message: "" }, approved_count: 1, total: 1, stale_count: 0,
      shots: [shot],
      queue: { paused: false, rows: [], total_shots: 0, total_s: 0, total_text: "", running: null },
    };
    stubFetch([(url) => (url.pathname === `${API}/shots` ? json(board) : undefined)]);
    const go = vi.fn();
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <ShotBoard projectId={ID} onContinue={go} />
      </QueryClientProvider>,
    );
    const btn = await screen.findByRole("button", { name: /continue to assembly/i });
    expect((btn as HTMLButtonElement).disabled).toBe(false);
    await userEvent.click(btn);
    expect(go).toHaveBeenCalled();
  });
});
