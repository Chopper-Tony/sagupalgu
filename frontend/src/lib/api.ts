import axios from "axios";
import type { SessionResponse } from "../types";

const BASE_URL = import.meta.env.VITE_API_URL ?? "/api/v1";

const client = axios.create({
  baseURL: BASE_URL,
  timeout: 120000,
});

// Dev 환경 자동 인증 (X-Dev-User-Id 헤더 주입)
client.interceptors.request.use((config) => {
  if (import.meta.env.DEV) {
    config.headers["X-Dev-User-Id"] = "seller-1";
  }
  return config;
});

export const api = {
  /** SSE 스트림 URL을 반환한다. EventSource에서 사용. */
  getSessionStreamUrl: (id: string) => `${BASE_URL}/sessions/${id}/stream`,

  createSession: () =>
    client.post<SessionResponse>("/sessions").then((r) => r.data),

  getSession: (id: string) =>
    client.get<SessionResponse>(`/sessions/${id}`).then((r) => r.data),

  uploadImages: (id: string, files: File[]) => {
    const form = new FormData();
    files.forEach((f) => form.append("files", f));
    return client
      .post<SessionResponse>(`/sessions/${id}/images`, form)
      .then((r) => r.data);
  },

  analyzeSession: (id: string) =>
    client.post<SessionResponse>(`/sessions/${id}/analyze`).then((r) => r.data),

  provideProductInfo: (id: string, productInfo: { model: string; brand?: string; category?: string }) =>
    client
      .post<SessionResponse>(`/sessions/${id}/provide-product-info`, productInfo)
      .then((r) => r.data),

  generateListing: (id: string) =>
    client
      .post<SessionResponse>(`/sessions/${id}/generate-listing`)
      .then((r) => r.data),

  rewriteListing: (id: string, instruction: string) =>
    client
      .post<SessionResponse>(`/sessions/${id}/rewrite-listing`, { instruction })
      .then((r) => r.data),

  updateListing: (id: string, listing: { title: string; description: string; price: number; tags?: string[] }) =>
    client
      .post<SessionResponse>(`/sessions/${id}/update-listing`, listing)
      .then((r) => r.data),

  preparePublish: (id: string, platforms: string[]) =>
    client
      .post<SessionResponse>(`/sessions/${id}/prepare-publish`, {
        platform_targets: platforms,
      })
      .then((r) => r.data),

  publish: (id: string) =>
    client.post<SessionResponse>(`/sessions/${id}/publish`).then((r) => r.data),

  updateSaleStatus: (id: string, saleStatus: string) =>
    client
      .post<SessionResponse>(`/sessions/${id}/sale-status`, { sale_status: saleStatus })
      .then((r) => r.data),

  getSellerTips: (id: string) =>
    client
      .post<{ session_id: string; tips: Array<{ category: string; message: string; priority: string }> }>(`/sessions/${id}/seller-tips`)
      .then((r) => r.data),

  // 플랫폼 연동
  getPlatformStatus: () =>
    client.get<{ platforms: Record<string, { name: string; connected: boolean; session_saved_at: string | null }> }>("/platforms/status")
      .then((r) => r.data),

  platformLogin: (platform: string) =>
    client.post<{ success: boolean; platform?: string; name?: string; error?: string }>(`/platforms/${platform}/login`, {}, { timeout: 360000 })
      .then((r) => r.data),

  startPlatformConnect: () =>
    client.post<{ connect_token: string; expires_at: number }>("/platforms/connect/start")
      .then((r) => r.data),

  // 마켓 (공개)
  getMarketItems: (limit = 20, offset = 0) =>
    client.get<{ items: import("../types/market").MarketItem[]; total: number; limit: number; offset: number }>(
      "/market", { params: { limit, offset } }
    ).then((r) => r.data),

  searchMarketItems: (params: import("../types/market").MarketSearchParams) =>
    client.get<import("../types/market").MarketListResponse>(
      "/market", { params }
    ).then((r) => r.data),

  getMarketItem: (sessionId: string) =>
    client.get<import("../types/market").MarketDetailItem>(
      `/market/${sessionId}`
    ).then((r) => r.data),

  submitInquiry: (sessionId: string, body: import("../types/market").InquiryRequest) =>
    client.post<{ success: boolean; inquiry_id: string; discord_sent: boolean }>(
      `/market/${sessionId}/inquiry`, body
    ).then((r) => r.data),

  // 판매자 전용 (인증 필요)
  getMyListings: (saleStatusFilter?: string) =>
    client.get<{ items: import("../types/market").MyListingItem[]; total: number }>(
      "/market/my-listings", { params: saleStatusFilter ? { sale_status_filter: saleStatusFilter } : {} }
    ).then((r) => r.data),

  updateSaleStatusMarket: (sessionId: string, saleStatus: string) =>
    client.patch<{ success: boolean; sale_status: string }>(
      `/market/my-listings/${sessionId}/status`, { sale_status: saleStatus }
    ).then((r) => r.data),

  getInquiries: (sessionId: string) =>
    client.get<{ listing: Record<string, unknown>; inquiries: import("../types/market").InquiryItem[]; total: number }>(
      `/market/my-listings/${sessionId}/inquiries`
    ).then((r) => r.data),

  replyToInquiry: (sessionId: string, inquiryId: string, reply: string) =>
    client.post<{ success: boolean; inquiry: import("../types/market").InquiryItem }>(
      `/market/my-listings/${sessionId}/inquiries/${inquiryId}/reply`, { reply }
    ).then((r) => r.data),

  relistListing: (sessionId: string, newPrice?: number) =>
    client.post<{ success: boolean; new_session: import("../types").SessionResponse }>(
      `/market/my-listings/${sessionId}/relist`, newPrice != null ? { new_price: newPrice } : {}
    ).then((r) => r.data),

  suggestReply: (sessionId: string, inquiryId: string) =>
    client.post<{ suggested_reply: string; inquiry_type: string; goal: string; source: string }>(
      `/market/my-listings/${sessionId}/inquiries/${inquiryId}/suggest-reply`
    ).then((r) => r.data),
};
