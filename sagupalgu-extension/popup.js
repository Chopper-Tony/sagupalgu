/**
 * Popup UI 로직 — 플랫폼 연결 + 상태 표시.
 * 토큰 자동 발급: 서버에서 토큰 발급 → 쿠키 수집 → 연결 (사용자 복사/붙여넣기 불필요).
 */

const DEFAULT_SERVER_URL = "http://34.239.155.255";

function getServerUrl() {
  return (document.getElementById("server-url")?.value || "").trim() || DEFAULT_SERVER_URL;
}

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

// 연결: 자동으로 토큰 발급 → 쿠키 수집 → 서버 전송
async function connect(platform) {
  const serverUrl = getServerUrl();
  const btn = document.getElementById(`btn-${platform}`);
  btn.disabled = true;
  btn.textContent = "연결 중...";
  clearMessage();

  try {
    // 1단계: 서버에서 토큰 자동 발급
    showMessage("토큰 발급 중...", "info");
    const tokenResp = await fetch(`${serverUrl}/api/v1/platforms/connect/start`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
    });
    if (!tokenResp.ok) throw new Error("토큰 발급 실패");
    const { connect_token } = await tokenResp.json();

    // 2단계: 쿠키 수집 + 서버 전송
    showMessage("플랫폼 쿠키 수집 중...", "info");
    chrome.runtime.sendMessage(
      { type: "CONNECT_PLATFORM", platform, connectToken: connect_token, serverUrl },
      (response) => {
        btn.disabled = false;
        btn.textContent = "연결";

        if (chrome.runtime.lastError) {
          showMessage(`오류: ${chrome.runtime.lastError.message}`, "error");
          return;
        }

        if (response.success && response.data.success) {
          showMessage(`${platform === "bunjang" ? "번개장터" : "중고나라"} 연결 성공!`, "success");
          updateStatus(platform, "connected");
        } else {
          const reason = response?.data?.reason || response?.error || "알 수 없는 오류";
          showMessage(
            `연결 실패: ${reason}. 해당 플랫폼에 먼저 로그인한 후 다시 시도하세요.`,
            "error"
          );
          updateStatus(platform, "reconnect_required");
        }
      }
    );
  } catch (e) {
    btn.disabled = false;
    btn.textContent = "연결";
    showMessage(`오류: ${e.message}`, "error");
  }
}

// 초기화
document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll(".connect-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const platform = btn.dataset.platform;
      if (platform) connect(platform);
    });
  });

  // 상태 조회
  const serverUrl = getServerUrl();
  chrome.runtime.sendMessage(
    { type: "CHECK_STATUS", serverUrl },
    (response) => {
      if (response && response.success && response.data.platforms) {
        for (const [key, info] of Object.entries(response.data.platforms)) {
          if (info.connected) updateStatus(key, "connected");
          else if (info.session_expired) updateStatus(key, "expired");
        }
      }
    }
  );
});
