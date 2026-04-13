/**
 * useWishlist 훅 테스트
 * - toggle, isWished, count 동작 검증
 * - localStorage 영속성 확인
 */
import { renderHook, act } from "@testing-library/react";
import { useWishlist } from "../useWishlist";

const STORAGE_KEY = "sagupalgu_wishlist";

beforeEach(() => {
  localStorage.clear();
});

describe("useWishlist", () => {
  it("초기 상태는 빈 위시리스트", () => {
    const { result } = renderHook(() => useWishlist());
    expect(result.current.count).toBe(0);
    expect(result.current.isWished("test-id")).toBe(false);
  });

  it("toggle로 아이템 추가/제거", () => {
    const { result } = renderHook(() => useWishlist());

    act(() => result.current.toggle("item-1"));
    expect(result.current.isWished("item-1")).toBe(true);
    expect(result.current.count).toBe(1);

    act(() => result.current.toggle("item-1"));
    expect(result.current.isWished("item-1")).toBe(false);
    expect(result.current.count).toBe(0);
  });

  it("여러 아이템 관리", () => {
    const { result } = renderHook(() => useWishlist());

    act(() => {
      result.current.toggle("a");
      result.current.toggle("b");
      result.current.toggle("c");
    });
    expect(result.current.count).toBe(3);
    expect(result.current.isWished("b")).toBe(true);
  });

  it("localStorage에 영속 저장", () => {
    const { result } = renderHook(() => useWishlist());
    act(() => result.current.toggle("persist-id"));

    const stored = JSON.parse(localStorage.getItem(STORAGE_KEY) || "[]");
    expect(stored).toContain("persist-id");
  });
});
