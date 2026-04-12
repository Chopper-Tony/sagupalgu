/**
 * Popup UI 로직 — 연결 버튼 + 상태 표시 + 자동 게시.
 */

const DEFAULT_SERVER_URL = "http://3.233.245.120";

function showMessage(text, type = "info") {
  const area = document.getElementById("message-area");
  area.innerHTML = `<div class="message message-${type}">${text}</div>`;
}

function clearMessage() {
  document.getElementById("message-area").innerHTML = "";
}

function updateStatus(platform, status) {
  const el = document.getElementById(`status-${platform}`);
  if (!el) return;

  if (status === "connected") {
    el.textContent = "연동됨";
    el.className = "platform-status status-connected";
  } else if (status === "expired" || status === "reconnect_required") {
    el.textContent = "재연결 필요";
    el.className = "platform-status status-expired";
  } else {
    el.textContent = "미연동";
    el.className = "platform-status status-disconnected";
  }
}

async function connect(platform) {
  const token = document.getElementById("token-input").value.trim();
  const serverUrl = document.getElementById("server-url").value.trim();

  if (!token) {
    showMessage("연결 토큰을 입력하세요. 웹앱에서 '계정 연결'을 눌러 발급받으세요.", "error");
    return;
  }

  const btn = document.getElementById(`btn-${platform}`);
  btn.disabled = true;
  btn.textContent = "연결 중...";
  clearMessage();
  showMessage("쿠키 수집 중...", "info");

  chrome.runtime.sendMessage(
    {
      type: "CONNECT_PLATFORM",
      platform,
      connectToken: token,
      serverUrl,
    },
    (response) => {
      btn.disabled = false;
      btn.textContent = "연결";

      if (chrome.runtime.lastError) {
        showMessage(`오류: ${chrome.runtime.lastError.message}`, "error");
        return;
      }

      if (response.success) {
        const data = response.data;
        if (data.success) {
          showMessage(`${platform} 연결 성공!`, "success");
          updateStatus(platform, "connected");
        } else {
          showMessage(
            `연결 실패: ${data.reason || "알 수 없는 오류"}. 해당 플랫폼에 먼저 로그인한 후 다시 시도하세요.`,
            "error"
          );
          updateStatus(platform, "reconnect_required");
        }
      } else {
        showMessage(`오류: ${response.error}`, "error");
      }
    }
  );
}

// ── 중고나라 익스텐션 게시 ──────────────────────────────────

async function startJoongnaPublish() {
  const sessionId = document.getElementById("session-id-input").value.trim();
  const serverUrl = document.getElementById("server-url").value.trim();
  const btn = document.getElementById("btn-publish-joongna");

  if (!sessionId) {
    showMessage("세션 ID를 입력하세요. 웹앱 URL에서 확인할 수 있습니다.", "error");
    return;
  }

  btn.disabled = true;
  btn.textContent = "게시 데이터 가져오는 중...";
  clearMessage();

  try {
    // 1. 서버에서 게시 데이터 가져오기
    const url = serverUrl || DEFAULT_SERVER_URL;
    const resp = await fetch(`${url}/api/v1/sessions/${sessionId}/publish-data`);
    if (!resp.ok) {
      const body = await resp.json().catch(() => ({}));
      throw new Error(body.detail || `서버 에러: ${resp.status}`);
    }
    const publishData = await resp.json();

    btn.textContent = "중고나라 페이지 여는 중...";
    showMessage(`"${publishData.title}" 자동 게시를 시작합니다...`, "info");

    // 2. background에 게시 요청
    chrome.runtime.sendMessage(
      {
        type: "PUBLISH_JOONGNA",
        publishData,
        sessionId,
        serverUrl: url,
      },
      (response) => {
        btn.disabled = false;
        btn.textContent = "중고나라 자동 게시 시작";

        if (chrome.runtime.lastError) {
          showMessage(`오류: ${chrome.runtime.lastError.message}`, "error");
          return;
        }

        if (response && response.success && response.data && response.data.success) {
          showMessage("중고나라 게시 성공!", "success");
        } else {
          const err = response?.data?.error || response?.error || "알 수 없는 오류";
          showMessage(`게시 실패: ${err}`, "error");
        }
      }
    );
  } catch (e) {
    btn.disabled = false;
    btn.textContent = "중고나라 자동 게시 시작";
    showMessage(`오류: ${e.message}`, "error");
  }
}

// ── 번개장터 익스텐션 게시 ──────────────────────────────────

async function startBunjangPublish() {
  const sessionId = document.getElementById("session-id-input").value.trim();
  const serverUrl = document.getElementById("server-url").value.trim();
  const btn = document.getElementById("btn-publish-bunjang");

  if (!sessionId) {
    showMessage("세션 ID를 입력하세요. 웹앱 URL에서 확인할 수 있습니다.", "error");
    return;
  }

  btn.disabled = true;
  btn.textContent = "게시 데이터 가져오는 중...";
  clearMessage();

  try {
    const url = serverUrl || DEFAULT_SERVER_URL;
    const resp = await fetch(`${url}/api/v1/sessions/${sessionId}/publish-data`);
    if (!resp.ok) {
      const body = await resp.json().catch(() => ({}));
      throw new Error(body.detail || `서버 에러: ${resp.status}`);
    }
    const publishData = await resp.json();

    btn.textContent = "번개장터 페이지 여는 중...";
    showMessage(`"${publishData.title}" 자동 게시를 시작합니다...`, "info");

    chrome.runtime.sendMessage(
      {
        type: "PUBLISH_BUNJANG",
        publishData,
        sessionId,
        serverUrl: url,
      },
      (response) => {
        btn.disabled = false;
        btn.textContent = "번개장터 자동 게시";

        if (chrome.runtime.lastError) {
          showMessage(`오류: ${chrome.runtime.lastError.message}`, "error");
          return;
        }

        if (response && response.success && response.data && response.data.success) {
          showMessage("번개장터 게시 성공!", "success");
        } else {
          const err = response?.data?.error || response?.error || "알 수 없는 오류";
          showMessage(`게시 실패: ${err}`, "error");
        }
      }
    );
  } catch (e) {
    btn.disabled = false;
    btn.textContent = "번개장터 자동 게시";
    showMessage(`오류: ${e.message}`, "error");
  }
}

// 초기화: 버튼 바인딩 + 상태 조회
document.addEventListener("DOMContentLoaded", () => {
  // 인라인 onclick 대신 addEventListener (Manifest V3 CSP 준수)
  document.querySelectorAll(".connect-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const platform = btn.dataset.platform;
      if (platform) connect(platform);
    });
  });

  // 게시 버튼
  document.getElementById("btn-publish-joongna").addEventListener("click", startJoongnaPublish);
  document.getElementById("btn-publish-bunjang").addEventListener("click", startBunjangPublish);

  const serverUrl = document.getElementById("server-url").value.trim();

  chrome.runtime.sendMessage(
    { type: "CHECK_STATUS", serverUrl },
    (response) => {
      if (response && response.success && response.data.platforms) {
        const platforms = response.data.platforms;
        for (const [key, info] of Object.entries(platforms)) {
          if (info.connected) {
            updateStatus(key, "connected");
          } else if (info.session_expired) {
            updateStatus(key, "expired");
          }
        }
      }
    }
  );
});
