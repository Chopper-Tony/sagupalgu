/**
 * AuthContext 스모크 테스트
 * - Supabase 미설정 환경: configured=false, loading 즉시 false, user null
 * - useAuth가 Provider 외부에서 호출되면 에러
 * - signOut은 supabase.auth.signOut 위임
 */
import { render, renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach } from "vitest";

// supabase 모듈 mock — 테스트마다 제어 가능하도록 factory 사용
vi.mock("../../lib/supabase", () => {
  let configured = false;
  const clientFactory = vi.fn();
  return {
    getSupabase: () => clientFactory(),
    isSupabaseConfigured: () => configured,
    __setConfigured: (v: boolean) => {
      configured = v;
    },
    __setClient: (c: unknown) => {
      clientFactory.mockReturnValue(c);
    },
  };
});

import { AuthProvider, useAuth } from "../AuthContext";
import * as supabaseModule from "../../lib/supabase";

type MockModule = typeof supabaseModule & {
  __setConfigured: (v: boolean) => void;
  __setClient: (c: unknown) => void;
};
const mocked = supabaseModule as unknown as MockModule;

describe("AuthContext — 미설정 환경", () => {
  beforeEach(() => {
    mocked.__setConfigured(false);
  });

  it("configured=false 시 loading 즉시 false, user/session null", async () => {
    const { result } = renderHook(() => useAuth(), {
      wrapper: ({ children }) => <AuthProvider>{children}</AuthProvider>,
    });
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.configured).toBe(false);
    expect(result.current.user).toBeNull();
    expect(result.current.session).toBeNull();
  });

  it("useAuth가 Provider 외부에서 호출되면 에러", () => {
    const spy = vi.spyOn(console, "error").mockImplementation(() => {});
    expect(() => renderHook(() => useAuth())).toThrow(/AuthProvider/);
    spy.mockRestore();
  });
});

describe("AuthContext — 설정된 환경", () => {
  beforeEach(() => {
    mocked.__setConfigured(true);
  });

  it("초기 getSession 호출로 세션을 복원한다", async () => {
    const unsubscribe = vi.fn();
    const fakeSession = { access_token: "tok", user: { id: "u1", email: "a@b.c" } };
    const fakeClient = {
      auth: {
        getSession: vi.fn().mockResolvedValue({ data: { session: fakeSession } }),
        onAuthStateChange: vi.fn().mockReturnValue({
          data: { subscription: { unsubscribe } },
        }),
        signInWithPassword: vi.fn(),
        signUp: vi.fn(),
        signInWithOAuth: vi.fn(),
        signOut: vi.fn().mockResolvedValue({ error: null }),
      },
    };
    mocked.__setClient(fakeClient);

    const { result } = renderHook(() => useAuth(), {
      wrapper: ({ children }) => <AuthProvider>{children}</AuthProvider>,
    });

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(fakeClient.auth.getSession).toHaveBeenCalled();
    expect(result.current.user?.id).toBe("u1");
    expect(result.current.session).toBeTruthy();
  });

  it("signOut 호출 시 supabase.auth.signOut 위임 + 로컬 상태 클리어", async () => {
    const fakeClient = {
      auth: {
        getSession: vi.fn().mockResolvedValue({ data: { session: null } }),
        onAuthStateChange: vi.fn().mockReturnValue({
          data: { subscription: { unsubscribe: vi.fn() } },
        }),
        signInWithPassword: vi.fn(),
        signUp: vi.fn(),
        signInWithOAuth: vi.fn(),
        signOut: vi.fn().mockResolvedValue({ error: null }),
      },
    };
    mocked.__setClient(fakeClient);

    const { result } = renderHook(() => useAuth(), {
      wrapper: ({ children }) => <AuthProvider>{children}</AuthProvider>,
    });
    await waitFor(() => expect(result.current.loading).toBe(false));

    await result.current.signOut();
    expect(fakeClient.auth.signOut).toHaveBeenCalled();
    expect(result.current.user).toBeNull();
    expect(result.current.session).toBeNull();
  });
});

describe("AuthProvider 렌더", () => {
  it("children을 그대로 렌더링한다", () => {
    mocked.__setConfigured(false);
    const { getByText } = render(
      <AuthProvider>
        <div>내부</div>
      </AuthProvider>,
    );
    expect(getByText("내부")).toBeDefined();
  });
});
