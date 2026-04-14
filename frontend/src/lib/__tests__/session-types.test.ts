/**
 * 세션 타입 계약 테스트
 * - SessionStatus 13개 상태 값 검증
 * - ProductCandidate, ConfirmedProduct, CanonicalListing 필드 확인
 */
import type { SessionStatus, ProductCandidate, ConfirmedProduct, CanonicalListing } from "../../types/session";

const ALL_STATUSES: SessionStatus[] = [
  "session_created",
  "images_uploaded",
  "awaiting_product_confirmation",
  "market_analyzing",
  "product_confirmed",
  "draft_generated",
  "awaiting_publish_approval",
  "publishing",
  "completed",
  "awaiting_sale_status_update",
  "optimization_suggested",
  "publishing_failed",
  "failed",
];

describe("SessionStatus", () => {
  it("13개 상태가 정의됨", () => {
    expect(ALL_STATUSES).toHaveLength(13);
  });

  it("터미널 상태 포함", () => {
    expect(ALL_STATUSES).toContain("completed");
    expect(ALL_STATUSES).toContain("failed");
  });
});

describe("ProductCandidate 계약", () => {
  it("필수 필드", () => {
    const candidate: ProductCandidate = {
      brand: "애플",
      model: "아이폰 15",
      category: "스마트폰",
      confidence: 0.95,
    };
    expect(candidate.confidence).toBeGreaterThan(0);
    expect(candidate.brand).toBeTruthy();
  });
});

describe("ConfirmedProduct 계약", () => {
  it("source는 user_input 또는 vision", () => {
    const p1: ConfirmedProduct = { brand: "삼성", model: "갤럭시", category: "스마트폰", source: "vision" };
    const p2: ConfirmedProduct = { brand: "삼성", model: "갤럭시", category: "스마트폰", source: "user_input" };
    expect(["vision", "user_input"]).toContain(p1.source);
    expect(["vision", "user_input"]).toContain(p2.source);
  });
});

describe("CanonicalListing 계약", () => {
  it("필수 필드 + 배열 타입", () => {
    const listing: CanonicalListing = {
      title: "테스트 상품",
      description: "설명",
      price: 50000,
      tags: ["태그1", "태그2"],
      images: ["/uploads/test.jpg"],
    };
    expect(listing.price).toBeGreaterThanOrEqual(0);
    expect(Array.isArray(listing.tags)).toBe(true);
    expect(Array.isArray(listing.images)).toBe(true);
  });
});
