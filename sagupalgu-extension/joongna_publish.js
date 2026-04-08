/**
 * Content Script — 중고나라 글쓰기 폼 자동 입력.
 *
 * background.js에서 FILL_JOONGNA_FORM 메시지를 받으면
 * 상품명/가격/설명/카테고리/이미지를 순서대로 입력하고 결과를 반환한다.
 *
 * 실행 조건: web.joongna.com/product/form* 페이지에서만 동작.
 */

(() => {
  "use strict";

  // ── 유틸리티 ─────────────────────────────────────────────

  function sleep(ms) {
    return new Promise((r) => setTimeout(r, ms));
  }

  /** 셀렉터가 DOM에 나타날 때까지 대기 (최대 timeout ms) */
  function waitFor(selector, timeout = 15000) {
    return new Promise((resolve, reject) => {
      const el = document.querySelector(selector);
      if (el) return resolve(el);

      const observer = new MutationObserver(() => {
        const found = document.querySelector(selector);
        if (found) {
          observer.disconnect();
          clearTimeout(timer);
          resolve(found);
        }
      });

      observer.observe(document.body, { childList: true, subtree: true });

      const timer = setTimeout(() => {
        observer.disconnect();
        reject(new Error(`waitFor("${selector}") 시간 초과 (${timeout}ms)`));
      }, timeout);
    });
  }

  /** input에 값을 채우고 React가 인식하도록 이벤트 발생 */
  function fillInput(el, value) {
    const nativeSet = Object.getOwnPropertyDescriptor(
      HTMLInputElement.prototype,
      "value"
    )?.set;
    if (nativeSet) {
      nativeSet.call(el, value);
    } else {
      el.value = value;
    }
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
  }

  /** textarea에 값을 채우고 React가 인식하도록 이벤트 발생 */
  function fillTextarea(el, value) {
    const nativeSet = Object.getOwnPropertyDescriptor(
      HTMLTextAreaElement.prototype,
      "value"
    )?.set;
    if (nativeSet) {
      nativeSet.call(el, value);
    } else {
      el.value = value;
    }
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
  }

  // ── 이미지 업로드 ────────────────────────────────────────

  /**
   * URL 배열을 File 객체로 변환 후 input[type=file]에 주입.
   * 서버에서 이미지 URL을 받아 fetch → Blob → File 변환.
   */
  async function uploadImages(imageUrls) {
    if (!imageUrls || imageUrls.length === 0) return;

    const fileInput = document.querySelector(
      "input[type='file'][accept*='image'], input[type='file'][multiple]"
    );
    if (!fileInput) {
      console.warn("[사구팔구] 이미지 업로드 input을 찾지 못함");
      return;
    }

    const files = [];
    for (const url of imageUrls) {
      try {
        const resp = await fetch(url);
        const blob = await resp.blob();
        const name = url.split("/").pop() || `image_${files.length}.jpg`;
        files.push(new File([blob], name, { type: blob.type || "image/jpeg" }));
      } catch (e) {
        console.warn(`[사구팔구] 이미지 다운로드 실패: ${url}`, e);
      }
    }

    if (files.length === 0) return;

    const dt = new DataTransfer();
    files.forEach((f) => dt.items.add(f));
    fileInput.files = dt.files;
    fileInput.dispatchEvent(new Event("change", { bubbles: true }));
    console.log(`[사구팔구] 이미지 ${files.length}개 업로드 완료`);
  }

  // ── 카테고리 선택 ────────────────────────────────────────

  async function selectCategory() {
    await sleep(1200);

    // 추천 카테고리 첫 항목 클릭 시도
    const selectors = [
      // "추천 카테고리" 텍스트 뒤의 첫 번째 버튼
      () => {
        const labels = document.querySelectorAll("*");
        for (const el of labels) {
          if (el.textContent.trim() === "추천 카테고리") {
            const next = el.nextElementSibling;
            if (next) {
              const btn = next.querySelector("button, [role='button']") || next;
              return btn;
            }
          }
        }
        return null;
      },
      // 일반적인 카테고리 버튼
      () =>
        document.querySelector(
          "div:has(> *:first-child:empty) button, .category-item button"
        ),
    ];

    for (const finder of selectors) {
      try {
        const el = typeof finder === "function" ? finder() : document.querySelector(finder);
        if (el) {
          el.scrollIntoView({ block: "center" });
          el.click();
          console.log("[사구팔구] 추천 카테고리 선택 완료");
          await sleep(1000);
          return true;
        }
      } catch (e) {
        continue;
      }
    }

    console.warn("[사구팔구] 추천 카테고리 자동 선택 실패 — 수동 선택 필요");
    return false;
  }

  // ── 메인 폼 입력 ─────────────────────────────────────────

  async function fillForm(data) {
    const steps = [];

    try {
      // 페이지 로딩 대기
      await sleep(2000);

      // 403 차단 감지
      if (document.title.includes("403") || document.body.innerText.includes("403 ERROR")) {
        throw new Error("중고나라 접속이 차단되었습니다.");
      }

      // ① 이미지 업로드
      steps.push("이미지 업로드");
      await uploadImages(data.image_urls);
      await sleep(1500);

      // ② 상품명
      steps.push("상품명 입력");
      const titleInput = await waitFor(
        "input[placeholder*='상품명'], input[placeholder*='제목']"
      );
      fillInput(titleInput, data.title);
      await sleep(1000);

      // ③ 카테고리
      steps.push("카테고리 선택");
      await selectCategory();
      await sleep(1000);

      // ④ 가격
      steps.push("가격 입력");
      const priceInput = await waitFor(
        "input[placeholder*='판매가격'], input[placeholder*='가격']"
      );
      fillInput(priceInput, String(data.price));
      await sleep(800);

      // ⑤ 설명
      steps.push("설명 입력");
      const textarea = document.querySelector("textarea");
      if (textarea) {
        fillTextarea(textarea, data.description);
        await sleep(800);
      }

      // ⑥ 상품 상태 (중고 선택)
      steps.push("상품 상태 선택");
      const condLabels = document.querySelectorAll(
        "label, button, [role='radio'], [role='button']"
      );
      for (const el of condLabels) {
        if (el.textContent.trim() === "중고") {
          el.click();
          await sleep(500);
          break;
        }
      }

      // ⑦ 판매하기 버튼 클릭
      steps.push("판매하기 클릭");
      await sleep(1000);
      const submitBtn = Array.from(document.querySelectorAll("button")).find(
        (b) => b.textContent.includes("판매하기")
      );

      if (!submitBtn) {
        throw new Error("판매하기 버튼을 찾지 못함");
      }

      submitBtn.scrollIntoView({ block: "center" });
      submitBtn.click();

      // ⑧ 결과 대기 — URL이 변경되면 성공
      steps.push("결과 대기");
      await sleep(4000);

      const currentUrl = window.location.href;
      if (currentUrl.includes("form?type=regist")) {
        throw new Error("등록 후에도 글쓰기 폼에 머뭄 — 필수 항목 누락 가능");
      }

      // 상품 ID 추출
      const match = currentUrl.match(/\/product\/(\d+)/) ||
                    currentUrl.match(/completeSeq=(\d+)/) ||
                    currentUrl.match(/\/(\d+)(?:\?|$)/);

      return {
        success: true,
        listing_url: currentUrl,
        listing_id: match ? match[1] : null,
        steps,
      };
    } catch (e) {
      return {
        success: false,
        error: e.message,
        steps,
      };
    }
  }

  // ── 메시지 리스너 ────────────────────────────────────────

  chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
    if (msg.type === "FILL_JOONGNA_FORM") {
      fillForm(msg.data)
        .then((result) => sendResponse(result))
        .catch((err) => sendResponse({ success: false, error: err.message }));
      return true; // async response
    }
  });

  console.log("[사구팔구] 중고나라 자동 게시 Content Script 로드됨");
})();
