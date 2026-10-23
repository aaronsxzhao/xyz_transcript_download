import { authFetch } from "./api";

export type FavoriteFolder = { id: number; title: string; count: number };
export type FavoriteVideo = {
  bvid: string;
  title: string;
  url: string;
  thumbnail: string;
  duration: number;
  uploader: string;
  available: boolean;
  imported: boolean;
};
export type FavoritePage = {
  videos: FavoriteVideo[];
  page: number;
  has_more: boolean;
};

async function read<T>(path: string, signal: AbortSignal): Promise<T> {
  const response = await authFetch("/api/bilibili-favorites" + path, {
    signal,
  });
  const body = await response.json().catch(() => null);
  if (!response.ok || !body)
    throw new Error(
      typeof body?.detail === "string"
        ? body.detail
        : "Could not load Bilibili favorites. Please retry.",
    );
  return body as T;
}
export const fetchFavoriteFolders = (signal: AbortSignal) =>
  read<{ folders: FavoriteFolder[] }>("", signal);
export const fetchFavoritePage = (
  folder: number,
  page: number,
  signal: AbortSignal,
) => read<FavoritePage>(`/${folder}?page=${page}`, signal);
