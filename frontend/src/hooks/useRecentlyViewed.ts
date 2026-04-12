import { useState, useCallback } from "react";

const STORAGE_KEY = "sagupalgu_recently_viewed";
const MAX_ITEMS = 5;

interface RecentItem {
  session_id: string;
  title: string;
  price: number;
  thumbnail: string;
}

function load(): RecentItem[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    return JSON.parse(raw);
  } catch {
    return [];
  }
}

function save(items: RecentItem[]) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(items));
}

export function useRecentlyViewed() {
  const [items, setItems] = useState<RecentItem[]>(load);

  const add = useCallback((item: { session_id: string; title: string; price: number; image_urls: string[] }) => {
    setItems((prev) => {
      const filtered = prev.filter((r) => r.session_id !== item.session_id);
      const next = [
        {
          session_id: item.session_id,
          title: item.title,
          price: item.price,
          thumbnail: item.image_urls?.[0] || "",
        },
        ...filtered,
      ].slice(0, MAX_ITEMS);
      save(next);
      return next;
    });
  }, []);

  return { items, add };
}
