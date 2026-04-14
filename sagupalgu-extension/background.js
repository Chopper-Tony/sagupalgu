/**
 * Service Worker — 서버 통신 담당.
 * popup.js에서 메시지를 받아 쿠키 수집 → 서버 전송.
 */

importScripts("cookies.js");

// 기본 서버 URL (배포 시 변경)
const DEFAULT_SERVER_URL = "http://44.221.49.47";

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

  if (msg.type === "PUBLISH_BUNJANG") {
    handleBunjangPublish(msg.publishData, msg.sessionId, msg.serverUrl)
      .then((result) => sendResponse({ success: true, data: result }))
      .catch((err) => sendResponse({ success: false, error: err.message }));
    return true;
  }

  if (msg.type === "FETCH_AND_PUBLISH") {
    handleFetchAndPublish(msg.sessionId, msg.platform, msg.serverUrl)
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

  // 2.5. CDP(Chrome DevTools Protocol)로 이미지 파일 업로드
  //      Content Script에서는 file input 보안 정책으로 불가능하므로
  //      debugger API로 DOM.setFileInputFiles를 직접 호출한다.
  let imageUploaded = false;
  console.log("[사구팔구] 이미지 URL 목록:", publishData.image_urls);
  if (publishData.image_urls && publishData.image_urls.length > 0) {
    try {
      console.log("[사구팔구] CDP 이미지 업로드 시작...");
      imageUploaded = await uploadImagesViaCDP(tab.id, publishData.image_urls, url);
      console.log("[사구팔구] CDP 이미지 업로드 결과:", imageUploaded);
    } catch (e) {
      console.error("[사구팔구] CDP 이미지 업로드 실패:", e.message, e.stack);
    }
  } else {
    console.warn("[사구팔구] 이미지 URL이 없음 — 이미지 업로드 스킵");
  }

  // 3. content script에 폼 입력 메시지 전송 (이미지는 CDP에서 처리 완료)
  const result = await chrome.tabs.sendMessage(tab.id, {
    type: "FILL_JOONGNA_FORM",
    data: { ...publishData, image_already_uploaded: imageUploaded },
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

/**
 * 번개장터 자동 게시: 새 탭 → content script로 폼 자동 입력 → 결과 서버 전송.
 * 중고나라와 동일 구조 — CDP 이미지 업로드 재사용.
 */
async function handleBunjangPublish(publishData, sessionId, serverUrl) {
  const url = serverUrl || DEFAULT_SERVER_URL;
  const WRITE_URL = "https://m.bunjang.co.kr/products/new";

  const tab = await chrome.tabs.create({ url: WRITE_URL, active: true });

  await new Promise((resolve) => {
    function listener(tabId, info) {
      if (tabId === tab.id && info.status === "complete") {
        chrome.tabs.onUpdated.removeListener(listener);
        resolve();
      }
    }
    chrome.tabs.onUpdated.addListener(listener);
  });

  await new Promise((r) => setTimeout(r, 2000));

  // CDP 이미지 업로드
  let imageUploaded = false;
  console.log("[사구팔구] [번개장터] 이미지 URL 목록:", publishData.image_urls);
  if (publishData.image_urls && publishData.image_urls.length > 0) {
    try {
      console.log("[사구팔구] [번개장터] CDP 이미지 업로드 시작...");
      imageUploaded = await uploadImagesViaCDP(tab.id, publishData.image_urls, url);
      console.log("[사구팔구] [번개장터] CDP 이미지 업로드 결과:", imageUploaded);
    } catch (e) {
      console.error("[사구팔구] [번개장터] CDP 이미지 업로드 실패:", e.message);
    }
  }

  // content script에 폼 입력 메시지 전송
  const result = await chrome.tabs.sendMessage(tab.id, {
    type: "FILL_BUNJANG_FORM",
    data: { ...publishData, image_already_uploaded: imageUploaded },
  });

  // 결과를 서버에 보고
  try {
    await fetch(`${url}/api/v1/sessions/${sessionId}/extension-publish-result`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        platform: "bunjang",
        success: result.success,
        listing_url: result.listing_url || null,
        listing_id: result.listing_id || null,
        error: result.error || null,
      }),
    });
  } catch (e) {
    console.warn("[사구팔구] [번개장터] 게시 결과 서버 전송 실패:", e);
  }

  return result;
}

/**
 * 웹앱 자동 게시 버튼용: 서버에서 데이터 fetch → 플랫폼별 게시 실행.
 * publish_bridge.js에서 호출됨.
 */
async function handleFetchAndPublish(sessionId, platform, serverUrl) {
  const url = serverUrl || DEFAULT_SERVER_URL;

  // 서버에서 게시 데이터 가져오기
  const resp = await fetch(`${url}/api/v1/sessions/${sessionId}/publish-data`);
  if (!resp.ok) {
    const body = await resp.json().catch(() => ({}));
    throw new Error(body.detail || `서버 에러: ${resp.status}`);
  }
  const publishData = await resp.json();

  // 플랫폼별 게시 실행
  if (platform === "bunjang") {
    return await handleBunjangPublish(publishData, sessionId, url);
  } else {
    return await handleJoongnaPublish(publishData, sessionId, url);
  }
}

/**
 * CDP Runtime.evaluate로 이미지를 base64 → File → input.files에 설정.
 * chrome.downloads 사용하지 않음 (탐색기 대화상자 문제 방지).
 *
 * 흐름:
 * 1. Background에서 fetch() → base64 변환
 * 2. CDP attach → Runtime.evaluate로 페이지 내에서 File 생성 + input.files 설정
 * 3. React fiber onChange 직접 호출
 * 4. detach
 */
async function uploadImagesViaCDP(tabId, imageUrls, serverUrl) {
  console.log("[사구팔구] uploadImagesViaCDP 시작", { tabId, imageUrls, serverUrl });

  // 1. 이미지를 fetch → base64 변환
  const base64Images = [];
  for (let i = 0; i < imageUrls.length; i++) {
    try {
      const imgUrl = imageUrls[i].startsWith("http")
        ? imageUrls[i]
        : `${serverUrl}${imageUrls[i]}`;
      console.log(`[사구팔구] 이미지 fetch 시도 (${i}):`, imgUrl);

      const resp = await fetch(imgUrl);
      if (!resp.ok) throw new Error(`fetch 실패: ${resp.status}`);
      const blob = await resp.blob();
      console.log(`[사구팔구] 이미지 fetch 성공 (${i}): ${blob.size} bytes`);

      const arrayBuffer = await blob.arrayBuffer();
      const base64 = btoa(
        new Uint8Array(arrayBuffer).reduce((s, b) => s + String.fromCharCode(b), "")
      );
      base64Images.push({
        base64,
        name: `image_${i}.jpg`,
        type: blob.type || "image/jpeg",
      });
    } catch (e) {
      console.error(`[사구팔구] 이미지 fetch 실패 (${i}):`, e.message);
    }
  }

  if (base64Images.length === 0) {
    console.warn("[사구팔구] 변환된 이미지 없음");
    return false;
  }

  // 2. CDP attach
  await chrome.debugger.attach({ tabId }, "1.3");

  try {
    // 3. Runtime.evaluate: base64 → File → DataTransfer → input.files + React onChange
    const { result } = await chrome.debugger.sendCommand({ tabId }, "Runtime.evaluate", {
      expression: `
        (function() {
          const images = ${JSON.stringify(base64Images)};
          const dt = new DataTransfer();

          for (const img of images) {
            const binary = atob(img.base64);
            const bytes = new Uint8Array(binary.length);
            for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
            dt.items.add(new File([bytes], img.name, { type: img.type }));
          }

          // file input 찾기
          const selectors = [
            "input[type='file'][accept*='image']",
            "input[type='file'][multiple]",
            "input[type='file']",
          ];
          let input = null;
          for (const sel of selectors) {
            input = document.querySelector(sel);
            if (input) break;
          }
          if (!input) return JSON.stringify({ ok: false, reason: 'input not found' });

          // files 설정
          input.files = dt.files;

          // 표준 이벤트만 발사 — React event delegation이 bubbling을 자동 처리
          // React fiber 직접 호출은 이중 업로드를 유발하므로 제거
          input.dispatchEvent(new Event('input', { bubbles: true }));
          input.dispatchEvent(new Event('change', { bubbles: true }));

          return JSON.stringify({
            ok: true,
            fileCount: dt.files.length,
            inputFiles: input.files.length,
          });
        })()
      `,
      returnByValue: true,
    });

    const evalResult = JSON.parse(result.value || '{"ok":false}');
    console.log("[사구팔구] CDP Runtime.evaluate 결과:", evalResult);

    if (!evalResult.ok) {
      console.warn("[사구팔구] CDP: 이미지 설정 실패:", evalResult.reason);
      return false;
    }

    console.log(`[사구팔구] CDP: 이미지 ${evalResult.fileCount}개 설정, React onChange: ${evalResult.reactCalled}`);
    await new Promise((r) => setTimeout(r, 2000));

    return true;
  } finally {
    try {
      await chrome.debugger.detach({ tabId });
    } catch (e) {
      // 이미 detach된 경우 무시
    }
  }
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
