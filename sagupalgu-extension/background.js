/**
 * Service Worker — 서버 통신 담당.
 * popup.js에서 메시지를 받아 쿠키 수집 → 서버 전송.
 */

importScripts("cookies.js");

// 기본 서버 URL (배포 시 변경)
const DEFAULT_SERVER_URL = "http://18.232.188.74";

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
 * chrome.downloads로 이미지를 로컬에 다운로드한 후
 * CDP DOM.setFileInputFiles로 로컬 파일 경로를 직접 설정.
 * Playwright set_input_files()와 동일한 원리.
 *
 * 흐름:
 * 1. chrome.downloads.download() → 사용자 Downloads 폴더에 저장
 * 2. chrome.debugger.attach → CDP 연결
 * 3. DOM.querySelector → file input 노드 찾기
 * 4. DOM.setFileInputFiles(files: [로컬 경로들]) → 파일 설정
 * 5. detach + 임시 파일 삭제
 */
async function uploadImagesViaCDP(tabId, imageUrls, serverUrl) {
  console.log("[사구팔구] uploadImagesViaCDP 시작", { tabId, imageUrls, serverUrl });

  // 1. 이미지를 로컬에 다운로드
  const downloadedPaths = [];
  const downloadIds = [];

  for (let i = 0; i < imageUrls.length; i++) {
    try {
      const imgUrl = imageUrls[i].startsWith("http")
        ? imageUrls[i]
        : `${serverUrl}${imageUrls[i]}`;
      console.log(`[사구팔구] 이미지 다운로드 시도 (${i}):`, imgUrl);

      const downloadId = await new Promise((resolve, reject) => {
        chrome.downloads.download(
          {
            url: imgUrl,
            filename: `sagupalgu_temp/image_${Date.now()}_${i}.jpg`,
            conflictAction: "uniquify",
          },
          (id) => {
            if (chrome.runtime.lastError) {
              reject(new Error(chrome.runtime.lastError.message));
            } else {
              resolve(id);
            }
          }
        );
      });

      downloadIds.push(downloadId);

      // 다운로드 완료 대기
      const filePath = await new Promise((resolve, reject) => {
        const timeout = setTimeout(() => reject(new Error("다운로드 시간 초과")), 30000);

        function onChanged(delta) {
          if (delta.id !== downloadId) return;
          if (delta.state && delta.state.current === "complete") {
            chrome.downloads.onChanged.removeListener(onChanged);
            clearTimeout(timeout);
            // 로컬 파일 경로 가져오기
            chrome.downloads.search({ id: downloadId }, (results) => {
              if (results && results[0]) {
                resolve(results[0].filename);
              } else {
                reject(new Error("다운로드 경로 조회 실패"));
              }
            });
          } else if (delta.state && delta.state.current === "interrupted") {
            chrome.downloads.onChanged.removeListener(onChanged);
            clearTimeout(timeout);
            reject(new Error("다운로드 중단"));
          }
        }

        chrome.downloads.onChanged.addListener(onChanged);
      });

      downloadedPaths.push(filePath);
      console.log(`[사구팔구] 이미지 다운로드 완료: ${filePath}`);
    } catch (e) {
      console.warn(`[사구팔구] 이미지 다운로드 실패 (${i}):`, e);
    }
  }

  if (downloadedPaths.length === 0) {
    console.warn("[사구팔구] 다운로드된 이미지 없음");
    return false;
  }

  // 2. CDP attach
  await chrome.debugger.attach({ tabId }, "1.3");

  try {
    // 3. DOM 활성화 + file input 찾기
    await chrome.debugger.sendCommand({ tabId }, "DOM.enable");
    const { root } = await chrome.debugger.sendCommand({ tabId }, "DOM.getDocument");

    const selectors = [
      "input[type='file'][accept*='image']",
      "input[type='file'][multiple]",
      "input[type='file']",
    ];

    let fileInputNodeId = null;
    for (const sel of selectors) {
      try {
        const { nodeId } = await chrome.debugger.sendCommand({ tabId }, "DOM.querySelector", {
          nodeId: root.nodeId,
          selector: sel,
        });
        if (nodeId) {
          fileInputNodeId = nodeId;
          break;
        }
      } catch (e) {
        continue;
      }
    }

    if (!fileInputNodeId) {
      console.warn("[사구팔구] CDP: file input 노드를 찾지 못함");
      return false;
    }

    // 4. DOM.setFileInputFiles — 로컬 파일 경로로 직접 설정 (Playwright 방식)
    await chrome.debugger.sendCommand({ tabId }, "DOM.setFileInputFiles", {
      nodeId: fileInputNodeId,
      files: downloadedPaths,
    });

    console.log(`[사구팔구] CDP: DOM.setFileInputFiles 완료 (${downloadedPaths.length}개)`);
    await new Promise((r) => setTimeout(r, 2000));

    return true;
  } finally {
    // 5. detach
    try {
      await chrome.debugger.detach({ tabId });
    } catch (e) {
      // 이미 detach된 경우 무시
    }

    // 6. 임시 다운로드 파일 삭제
    for (const id of downloadIds) {
      try {
        chrome.downloads.removeFile(id);
        chrome.downloads.erase({ id });
      } catch (e) {
        // 삭제 실패 무시
      }
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
