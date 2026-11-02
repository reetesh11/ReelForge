import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, queryKeys } from "./client";
import type { components } from "./schema";

export type LibraryCharacter = components["schemas"]["LibraryCharacterOut"];
export type LibraryPatch = { name?: string; aliases?: string[]; tags?: string[] };

export function useLibraryCharacters() {
  return useQuery({
    queryKey: queryKeys.library,
    queryFn: async (): Promise<LibraryCharacter[]> => {
      const { data } = await api.GET("/api/v1/library/characters");
      if (!data) throw new Error("could not load the library");
      return data;
    },
  });
}

export function useLibraryCharacter(id: string) {
  return useQuery({
    queryKey: queryKeys.libraryCharacter(id),
    queryFn: async (): Promise<LibraryCharacter> => {
      const { data } = await api.GET("/api/v1/library/characters/{cid}", {
        params: { path: { cid: id } },
      });
      if (!data) throw new Error("could not load that character");
      return data;
    },
  });
}

export function usePatchLibraryCharacter(id: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (body: LibraryPatch): Promise<LibraryCharacter> => {
      const { data, response } = await api.PATCH("/api/v1/library/characters/{cid}", {
        params: { path: { cid: id } },
        body,
      });
      if (!data) {
        const detail = (await response.clone().json().catch(() => ({}))) as { detail?: unknown };
        throw new Error(typeof detail.detail === "string" ? detail.detail : "could not save");
      }
      return data;
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.library });
    },
  });
}
