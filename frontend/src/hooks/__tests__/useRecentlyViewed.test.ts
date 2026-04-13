/**
 * useRecentlyViewed 훅 테스트
 * - add, items, 최대 5개 제한 확인
 * - 중복 추가 시 최상위 이동
 */
import { renderHook, act } from "@testing-library/react";
import { useRecentlyViewed } from "../useRecentlyViewed";

const STORAGE_KEY = "sagupalgu_recently_viewed";

beforeEach(() => {
  localStorage.clear();
});

function makeItem(id: string) {
  return { session_id: id, title: `상품 ${id}`, price: 10000, image_urls: [] };
}

describe("useRecentlyViewed", () => {
  it("초기 상태는 빈 리스트", () => {
    const { result } = renderHook(() => useRecentlyViewed());
    expect(result.current.items).toHaveLength(0);
  });

  it("아이템 추가", () => {
    const { result } = renderHook(() => useRecentlyViewed());
    act(() => result.current.add(makeItem("1")));
    expect(result.current.items).toHaveLength(1);
    expect(result.current.items[0].session_id).toBe("1");
  });

  it("최대 5개 제한", () => {
    const { result } = renderHook(() => useRecentlyViewed());
    act(() => {
      for (let i = 1; i <= 7; i++) {
        result.current.add(makeItem(String(i)));
      }
    });
    expect(result.current.items).toHaveLength(5);
    expect(result.current.items[0].session_id).toBe("7");
  });

  it("중복 추가 시 최상위로 이동", () => {
    const { result } = renderHook(() => useRecentlyViewed());
    act(() => {
      result.current.add(makeItem("a"));
      result.current.add(makeItem("b"));
      result.current.add(makeItem("a"));
    });
    expect(result.current.items).toHaveLength(2);
    expect(result.current.items[0].session_id).toBe("a");
  });

  it("localStorage에 영속 저장", () => {
    const { result } = renderHook(() => useRecentlyViewed());
    act(() => result.current.add(makeItem("persist")));

    const stored = JSON.parse(localStorage.getItem(STORAGE_KEY) || "[]");
    expect(stored).toHaveLength(1);
    expect(stored[0].session_id).toBe("persist");
  });
});
