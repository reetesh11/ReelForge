import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { expect, it, vi } from "vitest";
import { AppRoutes } from "@/AppRoutes";

it("renders the main navigation and redirects / to /projects", async () => {
  vi.stubGlobal("WebSocket", class {
    addEventListener() {}
    removeEventListener() {}
    close() {}
  });
  vi.stubGlobal("fetch", vi.fn(async () => new Response("[]", { status: 200, headers: { "Content-Type": "application/json" } })));
  render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter initialEntries={["/"]}>
        <AppRoutes />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  const nav = screen.getByRole("navigation", { name: "Main" });
  expect(within(nav).getAllByRole("link").map((l) => l.textContent)).toEqual(["Projects", "Settings & status", "Library"]);
  expect(await screen.findByRole("heading", { name: "Projects" })).toBeTruthy();
  vi.unstubAllGlobals();
});
