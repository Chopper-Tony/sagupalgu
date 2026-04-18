/**
 * #251: handleAutoPublish 가 postMessage 에 access_token 을 포함하는지.
 *
 * 익스텐션이 prod 로그인 사용자의 JWT 를 받아 백엔드 fetch 의 Authorization
 * 헤더로 사용. 토큰 없으면 백엔드가 dev-user 로 처리해 세션 소유자 mismatch → 404.
 */
import { vi, describe, it, expect, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";

// AuthContext mock — 토큰 시나리오 / 미로그인 시나리오 분기
const mockUseAuth = vi.fn();
vi.mock("../../../contexts/AuthContext", () => ({
  useAuth: () => mockUseAuth(),
}));

import { PublishResultCard } from "../PublishResultCard";

describe("PublishResultCard postMessage", () => {
  let postedMessages: any[];

  beforeEach(() => {
    postedMessages = [];
    vi.spyOn(window, "postMessage").mockImplementation((msg: any) => {
      postedMessages.push(msg);
    });
  });

  const baseResults = [
    { platform: "bunjang", source: "extension_required", success: false } as any,
  ];

  it("로그인된 사용자면 access_token 을 postMessage 에 포함", () => {
    mockUseAuth.mockReturnValue({
      session: { access_token: "supabase-jwt-abc123" },
    });

    render(
      <PublishResultCard
        results={baseResults}
        sessionId="sess-1"
        listing={null}
        onUpdateSaleStatus={() => {}}
      />
    );

    const btn = screen.getByRole("button", { name: /자동 게시|번개장터|게시/ });
    fireEvent.click(btn);

    expect(postedMessages.length).toBeGreaterThan(0);
    const msg = postedMessages[0];
    expect(msg.type).toBe("SAGUPALGU_PUBLISH");
    expect(msg.sessionId).toBe("sess-1");
    expect(msg.platform).toBe("bunjang");
    expect(msg.accessToken).toBe("supabase-jwt-abc123");
  });

  it("미로그인 (session=null) 이면 accessToken=null", () => {
    mockUseAuth.mockReturnValue({ session: null });

    render(
      <PublishResultCard
        results={baseResults}
        sessionId="sess-2"
        listing={null}
        onUpdateSaleStatus={() => {}}
      />
    );

    const btn = screen.getByRole("button", { name: /자동 게시|번개장터|게시/ });
    fireEvent.click(btn);

    const msg = postedMessages[0];
    expect(msg.accessToken).toBeNull();
  });
});
