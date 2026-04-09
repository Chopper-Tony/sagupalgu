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
  if (publishData.image_urls && publishData.image_urls.length > 0) {
    try {
      imageUploaded = await uploadImagesViaCDP(tab.id, publishData.image_urls, url);
    } catch (e) {
      console.warn("[사구팔구] CDP 이미지 업로드 실패:", e);
    }
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
 * CDP(Chrome DevTools Protocol)를 사용하여 file input에 이미지를 주입.
 * Playwright의 set_input_files()와 동일한 원리.
 *
 * 1. 이미지를 다운로드하여 로컬 임시 파일로 저장 (CDP는 로컬 파일 경로 필요 없음, base64 가능)
 * 2. chrome.debugger로 탭에 attach
 * 3. DOM.querySelector로 file input 노드 찾기
 * 4. DOM.setFileInputFiles로 파일 설정
 * 5. detach
 */
async function uploadImagesViaCDP(tabId, imageUrls, serverUrl) {
  // 1. 이미지 다운로드 → base64 변환
  const imageFiles = [];
  for (let i = 0; i < imageUrls.length; i++) {
    try {
      const imgUrl = imageUrls[i].startsWith("http")
        ? imageUrls[i]
        : `${serverUrl}${imageUrls[i]}`;
      const resp = await fetch(imgUrl);
      const blob = await resp.blob();
      const arrayBuffer = await blob.arrayBuffer();
      const base64 = btoa(
        new Uint8Array(arrayBuffer).reduce((s, b) => s + String.fromCharCode(b), "")
      );
      imageFiles.push({
        name: `image_${i}.jpg`,
        type: blob.type || "image/jpeg",
        base64,
      });
    } catch (e) {
      console.warn(`[사구팔구] 이미지 다운로드 실패 (${i}):`, e);
    }
  }

  if (imageFiles.length === 0) {
    console.warn("[사구팔구] 다운로드된 이미지 없음");
    return false;
  }

  // 2. CDP attach
  await chrome.debugger.attach({ tabId }, "1.3");

  try {
    // 3. DOM 활성화 + document 노드 가져오기
    await chrome.debugger.sendCommand({ tabId }, "DOM.enable");
    const { root } = await chrome.debugger.sendCommand({ tabId }, "DOM.getDocument");

    // 4. file input 찾기
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

    // 5. 각 이미지를 IO.read 없이 Network.enable + Page 경유로 업로드
    //    또는 Runtime.evaluate로 직접 파일 생성 후 input에 설정
    //
    //    CDP DOM.setFileInputFiles는 로컬 파일 경로가 필요한데,
    //    크롬 익스텐션에서는 로컬 경로 접근이 제한적이므로
    //    Runtime.evaluate로 base64 → File → DataTransfer → input.files 설정
    const base64Array = imageFiles.map((f) => ({
      base64: f.base64,
      name: f.name,
      type: f.type,
    }));

    await chrome.debugger.sendCommand({ tabId }, "Runtime.evaluate", {
      expression: `
        (async () => {
          const imageData = ${JSON.stringify(base64Array)};
          const dt = new DataTransfer();

          for (const img of imageData) {
            const binary = atob(img.base64);
            const bytes = new Uint8Array(binary.length);
            for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
            const file = new File([bytes], img.name, { type: img.type });
            dt.items.add(file);
          }

          const selectors = [
            "input[type='file'][accept*='image']",
            "input[type='file'][multiple]",
            "input[type='file']",
          ];

          let fileInput = null;
          for (const sel of selectors) {
            fileInput = document.querySelector(sel);
            if (fileInput) break;
          }

          if (!fileInput) throw new Error("file input not found");

          fileInput.files = dt.files;

          // React 감지를 위한 이벤트 발생
          const changeEvent = new Event("change", { bubbles: true });
          Object.defineProperty(changeEvent, "target", { value: fileInput });
          fileInput.dispatchEvent(changeEvent);

          // React 내부 핸들러가 input 이벤트를 감지하는 경우 대비
          fileInput.dispatchEvent(new Event("input", { bubbles: true }));

          return dt.files.length;
        })()
      `,
      awaitPromise: true,
      returnByValue: true,
    });

    console.log(`[사구팔구] CDP: 이미지 ${imageFiles.length}개 주입 완료`);

    // 잠시 대기 후 이미지 반영 확인
    await new Promise((r) => setTimeout(r, 2000));

    // 이미지가 반영되지 않았다면 추가 시도: 직접 input의 onchange 호출
    const { result: checkResult } = await chrome.debugger.sendCommand(
      { tabId },
      "Runtime.evaluate",
      {
        expression: `
          document.querySelectorAll("img[src*='blob:'], img[src*='data:'], [class*='preview'] img, [class*='thumb'] img").length
        `,
        returnByValue: true,
      }
    );

    if (checkResult.value === 0) {
      console.warn("[사구팔구] CDP: 이미지 반영 미확인, React 강제 트리거 시도");

      // React fiber 접근하여 onChange 직접 호출
      await chrome.debugger.sendCommand({ tabId }, "Runtime.evaluate", {
        expression: `
          (function() {
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
            if (!input) return;

            // React fiber에서 onChange 핸들러 찾기
            const keys = Object.keys(input);
            const reactKey = keys.find(k => k.startsWith("__reactFiber$") || k.startsWith("__reactInternalInstance$"));
            if (reactKey) {
              let fiber = input[reactKey];
              while (fiber) {
                if (fiber.memoizedProps && fiber.memoizedProps.onChange) {
                  fiber.memoizedProps.onChange({ target: input });
                  break;
                }
                fiber = fiber.return;
              }
            }
          })()
        `,
        returnByValue: true,
      });

      await new Promise((r) => setTimeout(r, 1000));
    }

    return true;
  } finally {
    // 6. detach
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
