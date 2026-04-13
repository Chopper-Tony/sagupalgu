/**
 * Content Script — 번개장터 글쓰기 폼 자동 입력.
 *
 * background.js에서 FILL_BUNJANG_FORM 메시지를 받으면
 * 상품명/가격/설명/카테고리/이미지를 순서대로 입력하고 결과를 반환한다.
 *
 * 실행 조건: m.bunjang.co.kr/products/new* 페이지에서만 동작.
 * 셀렉터 출처: legacy_spikes/secondhand_publisher/publishers/bunjang.py
 */

(() => {
  "use strict";

  // ── 유틸리티 ─────────────────────────────────────────────

  function sleep(ms) {
    return new Promise((r) => setTimeout(r, ms));
  }

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

  // ── 카테고리 선택 ────────────────────────────────────────

  async function selectCategory(category) {
    // 번개장터 products/new: 대분류 목록이 스크롤 가능한 3단 셀렉터로 노출
    // 매핑 실패 시 "기타"를 폴백으로 선택

    const FALLBACK = "기타";

    const categoryMap = {
      "스마트폰": "디지털",
      "태블릿": "디지털",
      "노트북": "디지털",
      "가전": "가전제품",
      "음향기기": "디지털",
      "카메라": "디지털",
      "패션": "남성의류",
      "문구": "도서/티켓/문구",
      "기타": FALLBACK,
    };

    const targetCategory = (category && categoryMap[category]) || FALLBACK;

    // 1단계: 카테고리 첫 번째 컬럼(대분류 스크롤 컨테이너) 찾기
    // "중분류 선택" 텍스트가 있는 영역의 왼쪽 형제 컬럼
    function findCategoryColumn() {
      // 스크롤 가능한 컨테이너를 찾는다 (overflow: auto/scroll + 세로 높이 200px 이상)
      const containers = document.querySelectorAll("ul, div, ol");
      for (const el of containers) {
        const style = getComputedStyle(el);
        const hasScroll = style.overflowY === "auto" || style.overflowY === "scroll";
        const tallEnough = el.offsetHeight >= 150;
        const hasCategories = el.textContent.includes("여성의류") && el.textContent.includes("남성의류");
        if (hasScroll && tallEnough && hasCategories) {
          return el;
        }
      }
      // 폴백: "여성의류" 텍스트를 포함하는 가장 작은 스크롤 컨테이너
      for (const el of containers) {
        if (el.scrollHeight > el.clientHeight && el.textContent.includes("여성의류")) {
          return el;
        }
      }
      return null;
    }

    // 2단계: 컨테이너 내부에서 텍스트 매칭 + 클릭
    function clickInColumn(column, name) {
      const items = column.querySelectorAll("li, a, span, div, p");
      for (const item of items) {
        // innerText로 비교 (렌더링된 텍스트만, 숨김 요소 제외)
        const text = (item.innerText || item.textContent || "").trim();
        if (text === name) {
          item.scrollIntoView({ block: "center" });
          item.click();
          // 클릭 이벤트가 안 먹힐 수 있으므로 mousedown+mouseup도 발사
          item.dispatchEvent(new MouseEvent("mousedown", { bubbles: true }));
          item.dispatchEvent(new MouseEvent("mouseup", { bubbles: true }));
          item.dispatchEvent(new MouseEvent("click", { bubbles: true }));
          return true;
        }
      }
      return false;
    }

    const column = findCategoryColumn();
    if (!column) {
      console.warn("[사구팔구] 카테고리 컬럼을 찾지 못함 — 수동 선택 필요");
      return;
    }

    console.log(`[사구팔구] 카테고리 컬럼 발견, scrollHeight=${column.scrollHeight}, clientHeight=${column.clientHeight}`);

    // 먼저 매핑된 카테고리 시도
    if (clickInColumn(column, targetCategory)) {
      console.log(`[사구팔구] 카테고리 선택: ${targetCategory} (원본: ${category || "없음"})`);
      await sleep(1000);
      return;
    }

    // 스크롤을 끝까지 내린 후 "기타" 폴백
    column.scrollTop = column.scrollHeight;
    await sleep(500);

    if (clickInColumn(column, FALLBACK)) {
      console.log(`[사구팔구] 카테고리 폴백 '${FALLBACK}' 선택 (원본: ${category || "없음"})`);
      await sleep(1000);
      return;
    }

    console.warn(`[사구팔구] 카테고리 '${FALLBACK}'도 찾지 못함 — 수동 선택 필요`);
    // 디버깅: 컬럼 내 모든 항목 출력
    const items = column.querySelectorAll("li, a, span, div");
    const texts = [...new Set([...items].map((i) => (i.innerText || "").trim()).filter(Boolean))];
    console.log(`[사구팔구] 컬럼 내 항목 목록:`, texts.slice(0, 30));
  }

  // ── 상태 선택 ────────────────────────────────────────────

  async function selectCondition() {
    // 상품상태 라디오 버튼 선택 (우선순위: 사용감 없음 > 사용감 적음)
    const targets = ["사용감 없음", "사용감 적음"];
    const labels = document.querySelectorAll("label");
    for (const target of targets) {
      for (const el of labels) {
        if (el.textContent.includes(target)) {
          // label 내부의 radio input 또는 label 자체 클릭
          const radio = el.querySelector("input[type='radio']");
          if (radio) {
            radio.click();
          } else {
            el.click();
          }
          console.log(`[사구팔구] 상태 선택: ${target}`);
          await sleep(300);
          return;
        }
      }
    }
    console.warn("[사구팔구] 상태 선택 실패 — 수동 선택 필요");
  }

  // ── 메인 폼 입력 ─────────────────────────────────────────

  async function fillForm(data) {
    const steps = [];

    try {
      await sleep(2000);

      // 로그인 확인
      if (window.location.href.includes("login")) {
        throw new Error("번개장터 로그인이 필요합니다.");
      }

      // ① 이미지 — CDP에서 처리 (content script에서 스킵)
      steps.push("이미지");
      if (data.image_already_uploaded) {
        console.log("[사구팔구] 이미지는 CDP에서 이미 업로드됨");
      } else {
        console.warn("[사구팔구] CDP 이미지 업로드 실패 — 수동 첨부 필요");
        // 배너 표시
        const banner = document.createElement("div");
        banner.id = "sagupalgu-image-notice";
        banner.style.cssText =
          "position:fixed;top:0;left:0;right:0;z-index:99999;background:#1e40af;color:#fff;" +
          "padding:16px;text-align:center;font-size:15px;font-weight:600;box-shadow:0 2px 8px rgba(0,0,0,0.3);";
        banner.textContent = "📷 이미지를 직접 첨부해주세요. 첨부 후 자동으로 진행됩니다.";
        document.body.prepend(banner);

        let waitCount = 0;
        while (waitCount < 15) {
          await sleep(2000);
          waitCount++;
          const imgs = document.querySelectorAll(
            "img[src*='blob:'], img[src*='data:'], [class*='preview'] img, [class*='thumb'] img"
          ).length;
          if (imgs > 0) {
            console.log(`[사구팔구] 이미지 ${imgs}개 감지`);
            break;
          }
        }
        banner.remove();
      }
      await sleep(1500);

      // ② 이미지 모달 닫기 (번개장터는 이미지 업로드 후 모달이 뜰 수 있음)
      const modalClose = document.querySelector(
        "button[aria-label='close'], button[aria-label='닫기'], [class*='modal'] button[class*='close']"
      );
      if (modalClose) {
        modalClose.click();
        await sleep(500);
      }

      // ③ 상품명 (검색창이 아닌 폼 내부 입력란)
      steps.push("상품명 입력");
      const titleInput = await waitFor(
        "input[placeholder='상품명을 입력해 주세요.']"
      );
      titleInput.scrollIntoView({ block: "center" });
      titleInput.focus();
      await sleep(300);
      fillInput(titleInput, data.title);
      await sleep(1000);

      // ④ 카테고리
      steps.push("카테고리 선택");
      await selectCategory(data.category);
      await sleep(1000);

      // ⑤ 상태
      steps.push("상태 선택");
      await selectCondition();
      await sleep(500);

      // ⑥ 설명
      steps.push("설명 입력");
      const textarea = document.querySelector("textarea");
      if (textarea) {
        // 번개장터는 textarea 클릭 후 focus 필요 (floating footer 버그 방지)
        textarea.scrollIntoView({ block: "center" });
        textarea.focus();
        await sleep(300);
        fillTextarea(textarea, data.description);
        await sleep(800);
      }

      // ⑦ 태그
      steps.push("태그 입력");
      if (data.tags && data.tags.length > 0) {
        const tagInput = document.querySelector(
          "input[placeholder*='태그'], input[placeholder*='태그를 입력']"
        );
        if (tagInput) {
          for (const tag of data.tags.slice(0, 5)) {
            fillInput(tagInput, tag);
            // 스페이스로 태그 확정
            tagInput.dispatchEvent(
              new KeyboardEvent("keydown", { key: " ", code: "Space", bubbles: true })
            );
            tagInput.dispatchEvent(
              new KeyboardEvent("keyup", { key: " ", code: "Space", bubbles: true })
            );
            await sleep(300);
          }
        }
      }

      // ⑧ 가격
      steps.push("가격 입력");
      const priceInput = await waitFor(
        "input[placeholder*='가격'], input[placeholder*='가격을 입력']"
      );
      fillInput(priceInput, String(data.price));
      await sleep(800);

      // ⑨ 이미지 확인 — CDP 성공이면 스킵
      steps.push("이미지 확인");
      if (!data.image_already_uploaded) {
        const fi = document.querySelector("input[type='file']");
        if (!fi || !fi.files || fi.files.length === 0) {
          console.warn("[사구팔구] 이미지 미첨부 상태 — 판매하기 전 확인 필요");
        }
      }

      // ⑩ 등록하기 버튼 클릭
      steps.push("등록하기 클릭");
      await sleep(1000);
      const submitBtn = Array.from(document.querySelectorAll("button")).find(
        (b) => b.textContent.includes("등록하기") || b.textContent.includes("등록")
      );

      if (!submitBtn) {
        throw new Error("등록하기 버튼을 찾지 못함");
      }

      submitBtn.scrollIntoView({ block: "center" });
      submitBtn.click();

      // ⑪ 결과 대기
      steps.push("결과 대기");
      await sleep(5000);

      const currentUrl = window.location.href;

      // 성공 검증: /products/숫자 패턴
      const match = currentUrl.match(/\/products\/(\d+)/);

      if (currentUrl.includes("products/new")) {
        throw new Error("등록 후에도 글쓰기 페이지에 머뭄 — 필수 항목 누락 가능");
      }

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
    if (msg.type === "FILL_BUNJANG_FORM") {
      fillForm(msg.data)
        .then((result) => sendResponse(result))
        .catch((err) => sendResponse({ success: false, error: err.message }));
      return true;
    }
  });

  console.log("[사구팔구] 번개장터 자동 게시 Content Script 로드됨");
})();
