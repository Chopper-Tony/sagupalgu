/**
 * Popup UI 로직 — 플랫폼 연결/해제 + 상태 표시.
 * 토큰 자동 발급: 서버에서 토큰 발급 → 쿠키 수집 → 연결.
 */

const DEFAULT_SERVER_URL = "http://34.239.155.255";

function getServerUrl() {
  return (document.getElementById("server-url")?.value || "").trim() || DEFAULT_SERVER_URL;
}

function showMessage(text, type = "info") {
  document.getElementById("message-area").innerHTML = `<div class="message message-${type}">${text}</div>`;
}

function clearMessage() {
  document.getElementById("message-area").innerHTML = "";
}

function updateStatus(platform, status) {
  const el = document.getElementById(`status-${platform}`);
  const connectBtn = document.getElementById(`btn-${platform}`);
  const disconnectBtn = document.getElementById(`btn-disconnect-${platform}`);
  if (!el) return;

  if (status === "connected") {
    el.textContent = "연동됨";
    el.className = "platform-status status-connected";
    if (connectBtn) connectBtn.style.display = "none";
    if (disconnectBtn) disconnectBtn.style.display = "inline-block";
  } else {
    el.textContent = status === "expired" ? "재연결 필요" : "미연동";
    el.className = status === "expired" ? "platform-status status-expired" : "platform-status status-disconnected";
    if (connectBtn) connectBtn.style.display = "inline-block";
    if (disconnectBtn) disconnectBtn.style.display = "none";
  }
}

// 연결
async function connect(platform) {
  const serverUrl = getServerUrl();
  const btn = document.getElementById(`btn-${platform}`);
  btn.disabled = true;
  btn.textContent = "연결 중...";
  clearMessage();

  try {
    showMessage("토큰 발급 중...", "info");
    const tokenResp = await fetch(`${serverUrl}/api/v1/platforms/connect/start`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
    });
    if (!tokenResp.ok) throw new Error("토큰 발급 실패");
    const { connect_token } = await tokenResp.json();

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
          const name = platform === "bunjang" ? "번개장터" : "중고나라";
          showMessage(`${name} 연결 성공!`, "success");
          updateStatus(platform, "connected");
        } else {
          const reason = response?.data?.reason || response?.error || "알 수 없는 오류";
          showMessage(`연결 실패: ${reason}. 해당 플랫폼에 먼저 로그인한 후 다시 시도하세요.`, "error");
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

// 연결 해제
async function disconnect(platform) {
  const serverUrl = getServerUrl();
  const btn = document.getElementById(`btn-disconnect-${platform}`);
  btn.disabled = true;
  clearMessage();

  try {
    const resp = await fetch(`${serverUrl}/api/v1/platforms/${platform}/disconnect`, {
      method: "POST",
    });
    // 서버에 disconnect 엔드포인트가 없어도 로컬 상태만 초기화
    const name = platform === "bunjang" ? "번개장터" : "중고나라";
    showMessage(`${name} 연결이 해제되었습니다.`, "info");
    updateStatus(platform, "disconnected");
  } catch {
    // 서버 호출 실패해도 UI는 해제 처리
    updateStatus(platform, "disconnected");
    showMessage("연결 해제됨 (서버 동기화는 다음 연결 시 갱신)", "info");
  } finally {
    btn.disabled = false;
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

  document.querySelectorAll(".disconnect-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const platform = btn.dataset.platform;
      if (platform) disconnect(platform);
    });
  });

  // 상태 조회
  chrome.runtime.sendMessage(
    { type: "CHECK_STATUS", serverUrl: getServerUrl() },
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
