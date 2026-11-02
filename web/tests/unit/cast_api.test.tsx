import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, expect, it, vi } from "vitest";
import { CastUnavailableError, useCast, useApproveCandidate } from "@/api/cast";
import { queryKeys } from "@/api/client";
import { json, stubFetch } from "../acceptance/helpers";

afterEach(() => vi.unstubAllGlobals());

function wrapper(client: QueryClient) {
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
}

it("nests the cast query key under stages so existing events refresh it", () => {
  expect(queryKeys.cast("p1")).toEqual([...queryKeys.stages("p1"), "cast"]);
});

it("reports CastUnavailableError for a 409 or 404", async () => {
  stubFetch([() => json({ detail: "Approve the story first." }, 409)]);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const { result } = renderHook(() => useCast("p1"), { wrapper: wrapper(client) });
  await waitFor(() => expect(result.current.isError).toBe(true));
  expect(result.current.error).toBeInstanceOf(CastUnavailableError);
});

it("posts the approval and surfaces the server detail on failure", async () => {
  const fn = stubFetch([
    (url, init) =>
      url.pathname === "/api/v1/projects/p1/cast/tomato:approve" && init?.method === "POST"
        ? json({ detail: "candidate not found" }, 404)
        : undefined,
  ]);
  const client = new QueryClient();
  const { result } = renderHook(() => useApproveCandidate("p1"), { wrapper: wrapper(client) });
  result.current.mutate({ key: "tomato", candidateId: "x" });
  await waitFor(() => expect(result.current.isError).toBe(true));
  expect(result.current.error?.message).toBe("candidate not found");
  expect(fn).toHaveBeenCalled();
});
