/**
 * 플랫폼별 쿠키 수집 + Playwright storage_state 변환.
 */

const PLATFORM_DOMAINS = {
  bunjang: ["bunjang.co.kr"],
  joongna: ["joongna.com"],
};

function convertSameSite(sameSite) {
  if (sameSite === "no_restriction") return "None";
  if (sameSite === "lax") return "Lax";
  if (sameSite === "strict") return "Strict";
  return "None";
}

/**
 * 지정 플랫폼의 쿠키를 수집하여 Playwright storage_state 형식으로 반환.
 * @param {string} platform - "bunjang" | "joongna"
 * @returns {Promise<{cookies: Array, origins: Array}>}
 * @throws {Error} 쿠키가 없으면 에러
 */
async function collectCookies(platform) {
  const domains = PLATFORM_DOMAINS[platform];
  if (!domains) {
    throw new Error(`지원하지 않는 플랫폼: ${platform}`);
  }

  // 전체 쿠키 → endsWith 도메인 필터링
  const allCookies = await chrome.cookies.getAll({});
  const filtered = allCookies.filter((c) =>
    domains.some((d) => c.domain.endsWith(d))
  );

  // 사전 체크: 쿠키가 없으면 로그인 안 된 상태
  if (filtered.length === 0) {
    throw new Error(
      "로그인 상태가 아닙니다. 먼저 해당 플랫폼에 로그인하세요."
    );
  }

  // Playwright storage_state 형식
  return {
    cookies: filtered.map((c) => ({
      name: c.name,
      value: c.value,
      domain: c.domain,
      path: c.path,
      expires: c.expirationDate || -1,
      httpOnly: c.httpOnly,
      secure: c.secure,
      sameSite: convertSameSite(c.sameSite),
    })),
    origins: [],
  };
}
