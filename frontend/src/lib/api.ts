import axios from "axios";
import type { SessionResponse } from "../types";

const BASE_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000/api/v1";

const client = axios.create({
  baseURL: BASE_URL,
  timeout: 120000,
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
};
