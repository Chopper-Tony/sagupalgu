/**
 * api 마켓/셀러 메서드 존재 + 타입 검증
 */
import { vi } from "vitest";

vi.mock("axios", () => {
  const mockClient = {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    interceptors: { request: { use: vi.fn() }, response: { use: vi.fn() } },
  };
  return { default: { create: vi.fn(() => mockClient) } };
});

import { api } from "../api";

describe("마켓 API 메서드", () => {
  it("getMarketItems", () => expect(typeof api.getMarketItems).toBe("function"));
  it("searchMarketItems", () => expect(typeof api.searchMarketItems).toBe("function"));
  it("getMarketItem", () => expect(typeof api.getMarketItem).toBe("function"));
  it("submitInquiry", () => expect(typeof api.submitInquiry).toBe("function"));
});

describe("셀러 대시보드 API 메서드", () => {
  it("getMyListings", () => expect(typeof api.getMyListings).toBe("function"));
  it("updateSaleStatusMarket", () => expect(typeof api.updateSaleStatusMarket).toBe("function"));
  it("getInquiries", () => expect(typeof api.getInquiries).toBe("function"));
  it("replyToInquiry", () => expect(typeof api.replyToInquiry).toBe("function"));
  it("relistListing", () => expect(typeof api.relistListing).toBe("function"));
  it("suggestReply", () => expect(typeof api.suggestReply).toBe("function"));
});

describe("플랫폼 연동 API 메서드", () => {
  it("getPlatformStatus", () => expect(typeof api.getPlatformStatus).toBe("function"));
  it("platformLogin", () => expect(typeof api.platformLogin).toBe("function"));
  it("startPlatformConnect", () => expect(typeof api.startPlatformConnect).toBe("function"));
  it("getSellerProfile", () => expect(typeof api.getSellerProfile).toBe("function"));
});
