/**
 * Content Script — 사구팔구 웹앱 페이지에 주입.
 *
 * 웹앱에서 window.postMessage로 보낸 게시 요청을
 * chrome.runtime.sendMessage로 background.js에 전달한다.
 *
 * 이를 통해 세션 ID 수동 복사 없이
 * 웹앱의 "자동 게시" 버튼 클릭 한 번으로 게시가 시작된다.
 */

(() => {
  "use strict";

  window.addEventListener("message", async (event) => {
    // 자기 자신의 메시지만 처리 (다른 origin 무시)
    if (event.source !== window) return;

    const msg = event.data;
    if (!msg || msg.type !== "SAGUPALGU_PUBLISH") return;

    const { sessionId, platform, serverUrl } = msg;
    if (!sessionId || !platform) return;

    console.log(`[사구팔구 Bridge] 게시 요청 수신: platform=${platform}, sessionId=${sessionId}`);

    try {
      // 1. 서버에서 게시 데이터 가져오기
      const url = serverUrl || window.location.origin;
      const resp = await fetch(`${url}/api/v1/sessions/${sessionId}/publish-data`);
      if (!resp.ok) {
        const body = await resp.json().catch(() => ({}));
        throw new Error(body.detail || `서버 에러: ${resp.status}`);
      }
      const publishData = await resp.json();

      // 2. background.js에 게시 요청 전달
      const msgType = platform === "bunjang" ? "PUBLISH_BUNJANG" : "PUBLISH_JOONGNA";

      chrome.runtime.sendMessage(
        {
          type: msgType,
          publishData,
          sessionId,
          serverUrl: url,
        },
        (response) => {
          // 결과를 웹앱에 전달
          window.postMessage({
            type: "SAGUPALGU_PUBLISH_RESULT",
            platform,
            sessionId,
            success: response?.success && response?.data?.success,
            error: response?.data?.error || response?.error || null,
          }, "*");
        }
      );
    } catch (e) {
      console.error(`[사구팔구 Bridge] 게시 요청 실패:`, e.message);
      window.postMessage({
        type: "SAGUPALGU_PUBLISH_RESULT",
        platform,
        sessionId,
        success: false,
        error: e.message,
      }, "*");
    }
  });

  console.log("[사구팔구 Bridge] Content Script 로드됨");
})();
