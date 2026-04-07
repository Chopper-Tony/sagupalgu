/**
 * api.ts 스모크 테스트
 * - axios client 설정 확인 (baseURL, timeout)
 * - getSessionStreamUrl URL 형식 검증
 */
import { vi } from "vitest";

// axios를 mock하여 실제 HTTP 요청 방지
vi.mock("axios", () => {
  const mockClient = {
    get: vi.fn(),
    post: vi.fn(),
  };
  return {
    default: {
      create: vi.fn(() => mockClient),
    },
  };
});

// mock 이후에 import해야 mock이 적용됨
import axios from "axios";
import { api } from "../api";

describe("axios client 설정", () => {
  it("axios.create가 baseURL과 timeout으로 호출된다", () => {
    expect(axios.create).toHaveBeenCalledWith(
      expect.objectContaining({
        baseURL: expect.any(String),
        timeout: 120000,
      })
    );
  });

  it("baseURL에 /api/v1이 포함된다", () => {
    const call = vi.mocked(axios.create).mock.calls[0]?.[0];
    expect(call?.baseURL).toContain("/api/v1");
  });
});

describe("getSessionStreamUrl", () => {
  it("세션 ID를 포함한 SSE URL을 반환한다", () => {
    const url = api.getSessionStreamUrl("test-session-123");
    expect(url).toContain("/sessions/test-session-123/stream");
  });

  it("baseURL로 시작한다", () => {
    const url = api.getSessionStreamUrl("abc");
    expect(url).toMatch(/\/api\/v1\/sessions\/abc\/stream$/);
  });
});

describe("api 객체", () => {
  it("필수 메서드들이 존재한다", () => {
    expect(typeof api.createSession).toBe("function");
    expect(typeof api.getSession).toBe("function");
    expect(typeof api.uploadImages).toBe("function");
    expect(typeof api.analyzeSession).toBe("function");
    expect(typeof api.generateListing).toBe("function");
    expect(typeof api.rewriteListing).toBe("function");
    expect(typeof api.preparePublish).toBe("function");
    expect(typeof api.publish).toBe("function");
    expect(typeof api.updateSaleStatus).toBe("function");
    expect(typeof api.getSessionStreamUrl).toBe("function");
  });
});
