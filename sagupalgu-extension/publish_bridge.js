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

  window.addEventListener("message", (event) => {
    // 자기 자신의 메시지만 처리
    if (event.source !== window) return;

    const msg = event.data;
    if (!msg || msg.type !== "SAGUPALGU_PUBLISH") return;

    const { sessionId, platform, serverUrl, accessToken } = msg;
    if (!sessionId || !platform) return;

    console.log(`[사구팔구 Bridge] 게시 요청 수신: platform=${platform}, sessionId=${sessionId}, hasToken=${!!accessToken}`);

    // background.js에 FETCH_AND_PUBLISH 메시지 전달
    // background가 서버에서 데이터를 가져와 게시까지 처리
    // accessToken (#251): prod Supabase JWT — 인증 필요 엔드포인트 호출용
    chrome.runtime.sendMessage(
      {
        type: "FETCH_AND_PUBLISH",
        sessionId,
        platform,
        serverUrl: serverUrl || window.location.origin,
        accessToken: accessToken || null,
      },
      (response) => {
        window.postMessage({
          type: "SAGUPALGU_PUBLISH_RESULT",
          platform,
          sessionId,
          success: response?.success && response?.data?.success,
          error: response?.data?.error || response?.error || null,
        }, "*");
      }
    );
  });

  console.log("[사구팔구 Bridge] Content Script 로드됨");
})();
