/**
 * Service Worker — 서버 통신 담당.
 * popup.js에서 메시지를 받아 쿠키 수집 → 서버 전송.
 */

importScripts("cookies.js");

// 기본 서버 URL (배포 시 변경)
const DEFAULT_SERVER_URL = "http://98.92.99.216";

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.type === "CONNECT_PLATFORM") {
    handleConnect(msg.platform, msg.connectToken, msg.serverUrl)
      .then((result) => sendResponse({ success: true, data: result }))
      .catch((err) => sendResponse({ success: false, error: err.message }));
    return true; // async response
  }

  if (msg.type === "CHECK_STATUS") {
    handleCheckStatus(msg.connectToken, msg.serverUrl)
      .then((result) => sendResponse({ success: true, data: result }))
      .catch((err) => sendResponse({ success: false, error: err.message }));
    return true;
  }

  if (msg.type === "PUBLISH_JOONGNA") {
    handleJoongnaPublish(msg.publishData, msg.sessionId, msg.serverUrl)
      .then((result) => sendResponse({ success: true, data: result }))
      .catch((err) => sendResponse({ success: false, error: err.message }));
    return true;
  }
});

async function handleConnect(platform, connectToken, serverUrl) {
  const url = serverUrl || DEFAULT_SERVER_URL;

  // 1. 쿠키 수집 + storage_state 변환
  const storageState = await collectCookies(platform);

  // 2. 서버에 전송 (30초 타임아웃)
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 30000);

  try {
    const response = await fetch(
      `${url}/api/v1/platforms/${platform}/connect`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          storage_state: storageState,
          connect_token: connectToken,
        }),
        signal: controller.signal,
      }
    );

    clearTimeout(timeout);

    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      throw new Error(body.detail || `서버 에러: ${response.status}`);
    }

    return await response.json();
  } catch (err) {
    clearTimeout(timeout);
    if (err.name === "AbortError") {
      throw new Error("서버 연결 시간 초과 (30초)");
    }
    throw err;
  }
}

/**
 * 중고나라 자동 게시: 새 탭 → content script로 폼 자동 입력 → 결과 서버 전송.
 */
async function handleJoongnaPublish(publishData, sessionId, serverUrl) {
  const url = serverUrl || DEFAULT_SERVER_URL;
  const WRITE_URL = "https://web.joongna.com/product/form?type=regist";

  // 1. 중고나라 글쓰기 페이지를 새 탭으로 열기
  const tab = await chrome.tabs.create({ url: WRITE_URL, active: true });

  // 2. 페이지 로딩 완료 대기
  await new Promise((resolve) => {
    function listener(tabId, info) {
      if (tabId === tab.id && info.status === "complete") {
        chrome.tabs.onUpdated.removeListener(listener);
        resolve();
      }
    }
    chrome.tabs.onUpdated.addListener(listener);
  });

  // content script 초기화 대기
  await new Promise((r) => setTimeout(r, 2000));

  // 3. content script에 폼 입력 메시지 전송
  const result = await chrome.tabs.sendMessage(tab.id, {
    type: "FILL_JOONGNA_FORM",
    data: publishData,
  });

  // 4. 결과를 서버에 보고
  try {
    await fetch(`${url}/api/v1/sessions/${sessionId}/extension-publish-result`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        platform: "joongna",
        success: result.success,
        listing_url: result.listing_url || null,
        listing_id: result.listing_id || null,
        error: result.error || null,
      }),
    });
  } catch (e) {
    console.warn("[사구팔구] 게시 결과 서버 전송 실패:", e);
  }

  return result;
}

async function handleCheckStatus(connectToken, serverUrl) {
  const url = serverUrl || DEFAULT_SERVER_URL;

  const response = await fetch(`${url}/api/v1/platforms/status`, {
    headers: { "Content-Type": "application/json" },
  });

  if (!response.ok) {
    throw new Error(`상태 조회 실패: ${response.status}`);
  }

  return await response.json();
}
