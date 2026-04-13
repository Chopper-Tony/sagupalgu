/**
 * 해시 라우팅 파싱 로직 테스트
 * App.tsx의 parseHash 로직을 추출하여 단위 테스트.
 * Error #300 재발 방지 — 훅 순서 위반이 발생했던 핵심 경로.
 */

type Page = "chat" | "market" | "market-detail" | "my-listings";

interface ParseResult {
  page: Page;
  marketDetailId: string | null;
}

/** App.tsx parseHash 로직과 동일 */
function parseHash(hash: string): ParseResult {
  const detailMatch = hash.match(/^#\/market\/(.+)$/);
  if (detailMatch) {
    return { page: "market-detail", marketDetailId: detailMatch[1] };
  } else if (hash === "#/market") {
    return { page: "market", marketDetailId: null };
  } else if (hash === "#/my-listings") {
    return { page: "my-listings", marketDetailId: null };
  } else {
    return { page: "chat", marketDetailId: null };
  }
}

describe("해시 라우팅 파싱", () => {
  it("#/ → chat", () => {
    expect(parseHash("#/")).toEqual({ page: "chat", marketDetailId: null });
  });

  it("#/market → market", () => {
    expect(parseHash("#/market")).toEqual({ page: "market", marketDetailId: null });
  });

  it("#/market/{id} → market-detail", () => {
    const result = parseHash("#/market/abc-123");
    expect(result.page).toBe("market-detail");
    expect(result.marketDetailId).toBe("abc-123");
  });

  it("#/my-listings → my-listings", () => {
    expect(parseHash("#/my-listings")).toEqual({ page: "my-listings", marketDetailId: null });
  });

  it("빈 해시 → chat", () => {
    expect(parseHash("")).toEqual({ page: "chat", marketDetailId: null });
  });

  it("알 수 없는 해시 → chat", () => {
    expect(parseHash("#/unknown")).toEqual({ page: "chat", marketDetailId: null });
  });

  it("UUID 형식 상세 ID", () => {
    const result = parseHash("#/market/96e056ef-564c-4755-94c1-b4b7be6ba60e");
    expect(result.page).toBe("market-detail");
    expect(result.marketDetailId).toBe("96e056ef-564c-4755-94c1-b4b7be6ba60e");
  });
});
