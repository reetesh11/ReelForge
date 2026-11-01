import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, expect, it, vi } from "vitest";
import { ProjectCard } from "@/components/ProjectCard";
import { ProjectsPage } from "@/routes/ProjectsPage";

afterEach(() => vi.unstubAllGlobals());

const project = {
  id: "01ARZ3NDEKTSV4RRFFQ69G5FAV",
  slug: "a",
  title: "Alpha",
  data_dir: "projects/a",
  stage: "DRAFT" as const,
  stages_approved: 2,
  brand_kit_id: null,
  created_at: "2026-11-01T10:00:00Z",
  updated_at: "2026-11-01T11:00:00Z",
};

it("renders a card with title link, stage count and time", () => {
  render(
    <MemoryRouter>
      <ul>
        <ProjectCard project={project} />
      </ul>
    </MemoryRouter>,
  );
  expect(screen.getByRole("link", { name: "Alpha" }).getAttribute("href")).toBe(`/projects/${project.id}`);
  expect(screen.getByText("2/6 stages approved")).toBeTruthy();
});

it("shows the empty state from the API", async () => {
  vi.stubGlobal("fetch", vi.fn(async () => new Response("[]", { headers: { "Content-Type": "application/json" } })));
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter>
        <ProjectsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  expect(await screen.findByText("No projects yet.")).toBeTruthy();
});
