/**
 * 마켓 타입 계약 테스트
 * - MarketItem, MyListingItem, InquiryItem 필드 존재 확인
 * - SaleStatus 유효 값 검증
 */
import type { MarketItem, MyListingItem, InquiryItem, SaleStatus } from "../../types/market";

describe("SaleStatus", () => {
  it("유효한 판매 상태 값", () => {
    const validStatuses: SaleStatus[] = ["available", "reserved", "sold"];
    expect(validStatuses).toHaveLength(3);
  });
});

describe("MarketItem 계약", () => {
  it("필수 필드 존재", () => {
    const item: MarketItem = {
      session_id: "test-id",
      title: "테스트 상품",
      description: "설명",
      price: 10000,
      image_urls: [],
      tags: [],
      published_platforms: [],
      sale_status: "available",
      category: "기타",
      created_at: null,
    };
    expect(item.session_id).toBeDefined();
    expect(item.price).toBeGreaterThanOrEqual(0);
    expect(Array.isArray(item.tags)).toBe(true);
    expect(Array.isArray(item.image_urls)).toBe(true);
  });
});

describe("MyListingItem 계약", () => {
  it("MarketItem 확장 + inquiry 필드", () => {
    const item: MyListingItem = {
      session_id: "test-id",
      title: "테스트",
      description: "설명",
      price: 5000,
      image_urls: [],
      tags: [],
      published_platforms: [],
      sale_status: "sold",
      category: "기타",
      created_at: null,
      inquiry_count: 3,
      unread_inquiry_count: 1,
    };
    expect(item.inquiry_count).toBe(3);
    expect(item.unread_inquiry_count).toBe(1);
  });
});

describe("InquiryItem 계약", () => {
  it("필수 필드 존재", () => {
    const inq: InquiryItem = {
      id: "inq-1",
      listing_id: "listing-1",
      listing_title: "상품명",
      listing_price: 10000,
      thumbnail_url: "",
      buyer_name: "구매자",
      buyer_contact: "010-1234-5678",
      message: "문의합니다",
      reply: null,
      status: "open",
      is_read: false,
      last_reply_at: null,
      created_at: "2026-04-13T00:00:00Z",
    };
    expect(inq.status).toBe("open");
    expect(inq.reply).toBeNull();
  });
});
