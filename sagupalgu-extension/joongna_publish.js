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
   * data URL 배열을 File 객체로 변환 후 이미지 업로드 영역에 주입.
   * background script에서 미리 다운로드한 data URL을 사용 (CORS 우회).
   *
   * 3단계 시도:
   * 1) input[type=file] 직접 설정 + change 이벤트
   * 2) 이미지 영역에 drag-and-drop 이벤트 시뮬레이션
   * 3) input.click() 인터셉트로 파일 주입
   */
  async function uploadImages(imageDataUrls) {
    if (!imageDataUrls || imageDataUrls.length === 0) {
      console.warn("[사구팔구] 업로드할 이미지 없음");
      return;
    }

    // data URL → File 객체 변환
    const files = [];
    for (let i = 0; i < imageDataUrls.length; i++) {
      try {
        const dataUrl = imageDataUrls[i];
        const resp = await fetch(dataUrl);
        const blob = await resp.blob();
        const ext = blob.type === "image/png" ? "png" : "jpg";
        files.push(new File([blob], `image_${i}.${ext}`, { type: blob.type || "image/jpeg" }));
      } catch (e) {
        console.warn(`[사구팔구] 이미지 변환 실패 (index ${i}):`, e);
      }
    }

    if (files.length === 0) {
      console.warn("[사구팔구] 변환된 이미지 파일 없음");
      return;
    }

    const dt = new DataTransfer();
    files.forEach((f) => dt.items.add(f));

    // ── 방법 1: input[type=file] 직접 설정 ──
    const fileInput = document.querySelector(
      "input[type='file'][accept*='image'], input[type='file'][multiple], input[type='file']"
    );

    if (fileInput) {
      fileInput.files = dt.files;
      const tracker = fileInput._valueTracker;
      if (tracker) tracker.setValue("");
      fileInput.dispatchEvent(new Event("change", { bubbles: true }));
      console.log("[사구팔구] 방법1: input.files 직접 설정 완료");
      await sleep(2000);
    }

    // 이미지 반영 확인
    const uploaded = document.querySelectorAll(
      "img[src*='blob:'], img[src*='data:'], [class*='image'] img, [class*='photo'] img, [class*='preview'] img"
    ).length;

    if (uploaded > 0) {
      console.log(`[사구팔구] 이미지 ${uploaded}개 반영 확인`);
      return;
    }

    // ── 방법 2: 드래그 앤 드롭 시뮬레이션 ──
    console.log("[사구팔구] 방법1 실패, 방법2: 드래그 앤 드롭 시도");

    // 이미지 업로드 드롭 영역 찾기 (카메라 아이콘 영역)
    const dropTargetSelectors = [
      "[class*='image-upload']",
      "[class*='photo-upload']",
      "[class*='file-upload']",
      "[class*='dropzone']",
      "[class*='camera']",
      "label[for]",
    ];

    let dropTarget = null;
    for (const sel of dropTargetSelectors) {
      dropTarget = document.querySelector(sel);
      if (dropTarget) break;
    }

    // 못 찾으면 "상품 이미지" 텍스트 근처 영역 사용
    if (!dropTarget) {
      const labels = document.querySelectorAll("*");
      for (const el of labels) {
        if (el.textContent && el.textContent.trim().startsWith("상품 이미지")) {
          dropTarget = el.parentElement || el;
          break;
        }
      }
    }

    if (dropTarget) {
      const dropDt = new DataTransfer();
      files.forEach((f) => dropDt.items.add(f));

      const dragEnter = new DragEvent("dragenter", { bubbles: true, dataTransfer: dropDt });
      const dragOver = new DragEvent("dragover", { bubbles: true, dataTransfer: dropDt });
      const drop = new DragEvent("drop", { bubbles: true, dataTransfer: dropDt });

      dropTarget.dispatchEvent(dragEnter);
      dropTarget.dispatchEvent(dragOver);
      dropTarget.dispatchEvent(drop);

      console.log("[사구팔구] 방법2: 드롭 이벤트 발생 완료");
      await sleep(2000);
    }

    // 다시 확인
    const uploaded2 = document.querySelectorAll(
      "img[src*='blob:'], img[src*='data:'], [class*='image'] img, [class*='photo'] img, [class*='preview'] img"
    ).length;

    if (uploaded2 > 0) {
      console.log(`[사구팔구] 이미지 ${uploaded2}개 반영 확인`);
      return;
    }

    // ── 방법 3: input.click() 인터셉트 ──
    console.log("[사구팔구] 방법2 실패, 방법3: click 인터셉트 시도");

    if (fileInput) {
      const origClick = HTMLInputElement.prototype.click;
      let intercepted = false;

      HTMLInputElement.prototype.click = function () {
        if (this.type === "file" && !intercepted) {
          intercepted = true;
          const dt3 = new DataTransfer();
          files.forEach((f) => dt3.items.add(f));
          this.files = dt3.files;
          this.dispatchEvent(new Event("change", { bubbles: true }));
          console.log("[사구팔구] 방법3: click 인터셉트로 파일 주입 성공");
        } else {
          origClick.call(this);
        }
      };

      // 카메라 영역 클릭하여 file input click 트리거
      const cameraArea = dropTarget || fileInput.closest("label") || fileInput.parentElement;
      if (cameraArea) {
        cameraArea.click();
        await sleep(1500);
      }

      HTMLInputElement.prototype.click = origClick;
    }

    console.log("[사구팔구] 이미지 업로드 3가지 방법 모두 시도 완료");
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

      // ① 이미지 업로드 (CDP에서 이미 처리된 경우 스킵)
      steps.push("이미지 업로드");
      if (data.image_already_uploaded) {
        console.log("[사구팔구] 이미지는 CDP에서 이미 업로드됨 — 스킵");
      } else {
        console.warn("[사구팔구] CDP 이미지 업로드 실패 — 수동 첨부 필요");
      }
      await sleep(2000);

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

      // ⑦ 이미지 첨부 확인 — 없으면 사용자에게 안내 후 대기
      steps.push("이미지 확인");
      const imageCheck = document.querySelectorAll(
        "img[src*='blob:'], img[src*='data:'], [class*='preview'] img, [class*='thumb'] img"
      ).length;

      if (imageCheck === 0) {
        console.warn("[사구팔구] 이미지 미첨부 — 사용자 수동 첨부 대기");
        const banner = document.createElement("div");
        banner.id = "sagupalgu-image-notice";
        banner.style.cssText =
          "position:fixed;top:0;left:0;right:0;z-index:99999;background:#1e40af;color:#fff;" +
          "padding:16px;text-align:center;font-size:15px;font-weight:600;box-shadow:0 2px 8px rgba(0,0,0,0.3);";
        banner.textContent = "📷 이미지를 직접 첨부해주세요. 첨부 후 자동으로 진행됩니다.";
        document.body.prepend(banner);

        // 사용자가 이미지 첨부할 때까지 최대 60초 대기
        let waitCount = 0;
        while (waitCount < 30) {
          await sleep(2000);
          waitCount++;
          const imgs = document.querySelectorAll(
            "img[src*='blob:'], img[src*='data:'], [class*='preview'] img, [class*='thumb'] img"
          ).length;
          if (imgs > 0) {
            console.log(`[사구팔구] 이미지 ${imgs}개 감지 — 계속 진행`);
            break;
          }
        }
        banner.remove();

        // ⑦-1. 중고나라 AI가 폼을 덮어쓴 경우 원래 데이터로 재입력
        console.log("[사구팔구] 이미지 첨부 후 중고나라 AI 덮어쓰기 복원 대기");
        await sleep(1500); // 중고나라 AI 처리 대기

        steps.push("폼 내용 복원");

        // 상품명 복원
        const titleRestore = document.querySelector(
          "input[placeholder*='상품명'], input[placeholder*='제목']"
        );
        if (titleRestore && data.title) {
          fillInput(titleRestore, data.title);
          await sleep(500);
        }

        // 가격 복원
        const priceRestore = document.querySelector(
          "input[placeholder*='판매가격'], input[placeholder*='가격']"
        );
        if (priceRestore && data.price) {
          fillInput(priceRestore, String(data.price));
          await sleep(500);
        }

        // 설명 복원
        const textareaRestore = document.querySelector("textarea");
        if (textareaRestore && data.description) {
          fillTextarea(textareaRestore, data.description);
          await sleep(500);
        }

        console.log("[사구팔구] 폼 내용 복원 완료");
      }

      // ⑧ 판매하기 버튼 클릭
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
