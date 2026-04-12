import { useState, useCallback } from "react";

const STORAGE_KEY = "sagupalgu_wishlist";

function loadWishlist(): Set<string> {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return new Set();
    return new Set(JSON.parse(raw));
  } catch {
    return new Set();
  }
}

function saveWishlist(ids: Set<string>) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify([...ids]));
}

export function useWishlist() {
  const [wishlist, setWishlist] = useState<Set<string>>(loadWishlist);

  const toggle = useCallback((sessionId: string) => {
    setWishlist((prev) => {
      const next = new Set(prev);
      if (next.has(sessionId)) {
        next.delete(sessionId);
      } else {
        next.add(sessionId);
      }
      saveWishlist(next);
      return next;
    });
  }, []);

  const isWished = useCallback(
    (sessionId: string) => wishlist.has(sessionId),
    [wishlist]
  );

  const count = wishlist.size;

  return { toggle, isWished, count, wishlist };
}
