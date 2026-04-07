/**
 * Popup UI 로직 — 연결 버튼 + 상태 표시.
 */

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

// 초기화: 상태 조회
document.addEventListener("DOMContentLoaded", () => {
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
