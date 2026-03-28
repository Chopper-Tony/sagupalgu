/**
 * sessionStatusUiMap 스모크 테스트
 * - 13개 상태 매핑 존재 확인
 * - getStatusUiConfig 반환 shape 검증
 * - statusLabel / platformLabel 정상 동작
 */
import {
  SESSION_STATUS_UI_MAP,
  getStatusUiConfig,
  isPollingStatus,
  isTerminalStatus,
  platformLabel,
  statusLabel,
  PROGRESS_COPY,
} from "../sessionStatusUiMap";
import type { SessionStatus } from "../../types";

// 백엔드 session_status.py 와 1:1 대응하는 13개 상태
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

describe("SESSION_STATUS_UI_MAP", () => {
  it("13개 상태 전부 매핑이 존재한다", () => {
    const keys = Object.keys(SESSION_STATUS_UI_MAP);
    expect(keys).toHaveLength(13);
    for (const status of ALL_STATUSES) {
      expect(SESSION_STATUS_UI_MAP).toHaveProperty(status);
    }
  });

  it("각 매핑은 card, composerMode, polling, autoProgress 필드를 가진다", () => {
    for (const status of ALL_STATUSES) {
      const config = SESSION_STATUS_UI_MAP[status];
      expect(config).toHaveProperty("card");
      expect(config).toHaveProperty("composerMode");
      expect(typeof config.polling).toBe("boolean");
      expect(typeof config.autoProgress).toBe("boolean");
    }
  });
});

describe("getStatusUiConfig", () => {
  it("상태에 맞는 config를 반환한다", () => {
    const config = getStatusUiConfig("session_created");
    expect(config.card).toBe("ImageUploadCard");
    expect(config.composerMode).toBe("upload");
    expect(config.polling).toBe(false);
  });

  it("draft_generated는 DraftCard + rewrite 모드", () => {
    const config = getStatusUiConfig("draft_generated");
    expect(config.card).toBe("DraftCard");
    expect(config.composerMode).toBe("rewrite");
  });
});

describe("isPollingStatus", () => {
  it("처리 중 상태(images_uploaded, publishing 등)는 true", () => {
    expect(isPollingStatus("images_uploaded")).toBe(true);
    expect(isPollingStatus("publishing")).toBe(true);
    expect(isPollingStatus("market_analyzing")).toBe(true);
  });

  it("사용자 대기 상태는 false", () => {
    expect(isPollingStatus("session_created")).toBe(false);
    expect(isPollingStatus("draft_generated")).toBe(false);
    expect(isPollingStatus("completed")).toBe(false);
  });
});

describe("isTerminalStatus", () => {
  it("optimization_suggested, failed는 터미널 상태", () => {
    expect(isTerminalStatus("optimization_suggested")).toBe(true);
    expect(isTerminalStatus("failed")).toBe(true);
  });

  it("completed는 터미널이 아님 (sale_status 업데이트 가능)", () => {
    expect(isTerminalStatus("completed")).toBe(false);
  });
});

describe("platformLabel", () => {
  it("bunjang → 번개장터", () => {
    expect(platformLabel("bunjang")).toBe("번개장터");
  });

  it("joongna → 중고나라", () => {
    expect(platformLabel("joongna")).toBe("중고나라");
  });

  it("daangn → 당근마켓", () => {
    expect(platformLabel("daangn")).toBe("당근마켓");
  });

  it("매핑 없는 코드는 원본 반환", () => {
    expect(platformLabel("unknown_platform")).toBe("unknown_platform");
  });
});

describe("statusLabel", () => {
  it("session_created → 생성됨", () => {
    expect(statusLabel("session_created")).toBe("생성됨");
  });

  it("completed → 게시 완료", () => {
    expect(statusLabel("completed")).toBe("게시 완료");
  });

  it("매핑 없는 상태는 원본 반환", () => {
    expect(statusLabel("unknown_status")).toBe("unknown_status");
  });
});

describe("PROGRESS_COPY", () => {
  it("폴링 상태에 대한 진행 카피가 정의되어 있다", () => {
    expect(PROGRESS_COPY.images_uploaded).toBeDefined();
    expect(PROGRESS_COPY.publishing).toBeDefined();
    expect(PROGRESS_COPY.images_uploaded?.title).toBeTruthy();
    expect(PROGRESS_COPY.images_uploaded?.subtitle).toBeTruthy();
  });
});
