"""
당근마켓 (Daangn) Publisher
- 플랫폼: Android 앱 (com.towneers.www)
- 자동화: uiautomator2 (ADB 기반 Python 라이브러리)
- 로그인: 전화번호 SMS 인증 (최초 1회, 이후 자동)
- 이미지: 갤러리에서 선택 또는 adb push 후 선택
- 제약: 실제 Android 디바이스 또는 에뮬레이터 필요
        GPS 기반 동네 인증 필요

설치:
    pip install uiautomator2
    python -m uiautomator2 init  # 디바이스에 에이전트 설치

연결:
    adb devices  # 디바이스 연결 확인
"""
import logging
import time
from pathlib import Path
from typing import Optional

from ..core.models import ListingPackage, PublishResult, Platform, ProductCondition

logger = logging.getLogger(__name__)

DAANGN_PACKAGE = "com.towneers.www"

CONDITION_MAP = {
    ProductCondition.NEW: "미개봉",
    ProductCondition.LIKE_NEW: "거의 새것",
    ProductCondition.GOOD: "상태 좋음",
    ProductCondition.FAIR: "보통",
    ProductCondition.POOR: "나쁨",
}


class DaangnPublisher:
    """
    당근마켓 Android 앱 자동화 Publisher
    uiautomator2 기반
    """

    def __init__(
        self,
        device_serial: Optional[str] = None,  # None = 첫 번째 연결 디바이스
        screenshot_dir: Path = Path("./screenshots"),
        image_push_dir: str = "/sdcard/DCIM/AutoSell",  # 이미지 push 경로
    ):
        self.device_serial = device_serial
        self.screenshot_dir = screenshot_dir
        self.image_push_dir = image_push_dir
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)
        self._d = None  # uiautomator2 device 객체

    def _connect(self):
        """디바이스 연결"""
        try:
            import uiautomator2 as u2
            if self.device_serial:
                self._d = u2.connect(self.device_serial)
            else:
                self._d = u2.connect()
            logger.info(f"[당근] 디바이스 연결: {self._d.device_info.get('productName', 'Unknown')}")
        except ImportError:
            raise RuntimeError(
                "uiautomator2 미설치. 다음 명령어로 설치하세요:\n"
                "  pip install uiautomator2\n"
                "  python -m uiautomator2 init"
            )

    def _screenshot(self, name: str) -> Path:
        path = self.screenshot_dir / f"daangn_{name}.png"
        self._d.screenshot(str(path))
        return path

    def _wait_and_click(self, text: str = None, resource_id: str = None,
                        xpath: str = None, timeout: int = 10):
        """요소 대기 후 클릭"""
        d = self._d
        if text:
            el = d(text=text)
        elif resource_id:
            el = d(resourceId=resource_id)
        elif xpath:
            el = d.xpath(xpath)
        else:
            raise ValueError("text, resource_id, xpath 중 하나 필요")

        if not el.wait(timeout=timeout):
            raise TimeoutError(f"요소 대기 시간 초과: text={text}, id={resource_id}")
        el.click()
        time.sleep(0.5)

    def _push_images(self, image_paths: list[Path]) -> list[str]:
        """
        이미지를 Android 디바이스 갤러리 경로에 push
        반환: 디바이스 내 경로 목록
        """
        import subprocess
        # push 디렉토리 생성
        subprocess.run(["adb", "shell", "mkdir", "-p", self.image_push_dir], check=True)

        device_paths = []
        for local_path in image_paths[:10]:
            if not local_path.exists():
                continue
            device_path = f"{self.image_push_dir}/{local_path.name}"
            subprocess.run(
                ["adb", "push", str(local_path), device_path],
                check=True, capture_output=True
            )
            # 미디어 스캔 갱신
            subprocess.run([
                "adb", "shell", "am", "broadcast",
                "-a", "android.intent.action.MEDIA_SCANNER_SCAN_FILE",
                "-d", f"file://{device_path}"
            ], capture_output=True)
            device_paths.append(device_path)

        time.sleep(1)  # 미디어 스캔 완료 대기
        logger.info(f"[당근] 이미지 {len(device_paths)}장 push 완료")
        return device_paths

    # ─────────────────────────────────────────
    # 로그인 확인
    # ─────────────────────────────────────────

    def is_logged_in(self) -> bool:
        """당근 앱 로그인 상태 확인"""
        d = self._d
        d.app_start(DAANGN_PACKAGE)
        time.sleep(2)

        # 로그인 화면 여부 확인
        # 비로그인: "전화번호로 시작하기" 버튼 존재
        login_btn = d(text="전화번호로 시작하기")
        if login_btn.exists:
            return False

        # 메인 화면 여부 확인 (하단 탭바 존재)
        home_tab = d(text="홈") or d(resourceId=f"{DAANGN_PACKAGE}:id/home_tab")
        return home_tab.exists

    # ─────────────────────────────────────────
    # 앱 내 글쓰기 버튼 찾기
    # ─────────────────────────────────────────

    def _navigate_to_write(self):
        """홈 → 글쓰기 버튼 클릭"""
        d = self._d

        # 하단 "글쓰기" 또는 "+" 버튼
        # 당근 앱에서 하단 중앙 + 버튼
        write_btn = (
            d(description="글쓰기") or
            d(text="글쓰기") or
            d(resourceId=f"{DAANGN_PACKAGE}:id/write_button") or
            d(resourceId=f"{DAANGN_PACKAGE}:id/btn_write")
        )

        if not write_btn.exists(timeout=5):
            # 홈 탭으로 이동 후 재시도
            d(text="홈").click()
            time.sleep(1)
            write_btn = d(description="글쓰기")

        write_btn.click()
        time.sleep(1)

        # "중고거래 글쓰기" 선택 (커뮤니티 글쓰기와 구분)
        trade_write = d(text="중고거래 글쓰기")
        if trade_write.exists(timeout=3):
            trade_write.click()
            time.sleep(1)

    # ─────────────────────────────────────────
    # 이미지 선택
    # ─────────────────────────────────────────

    def _select_images(self, image_paths: list[Path]):
        """
        당근 글쓰기 화면에서 이미지 선택
        이미지는 미리 디바이스에 push 되어 있어야 함
        """
        d = self._d

        # 사진 추가 버튼
        photo_btn = (
            d(text="사진") or
            d(description="사진 추가") or
            d(resourceId=f"{DAANGN_PACKAGE}:id/photo_add_btn")
        )

        if not photo_btn.exists(timeout=5):
            logger.warning("[당근] 사진 추가 버튼 미발견")
            return

        photo_btn.click()
        time.sleep(1)

        # 갤러리에서 이미지 선택
        # push된 이미지들이 갤러리에 나타남
        for i, img_path in enumerate(image_paths[:10]):
            # 파일명으로 이미지 탐색 (갤러리 뷰)
            img_el = d(text=img_path.name) or d(description=img_path.stem)
            if img_el.exists(timeout=3):
                img_el.click()
                time.sleep(0.3)
            else:
                # 위치 기반으로 선택 (갤러리 첫 번째 항목)
                if i == 0:
                    # 갤러리의 첫 번째 이미지 탭
                    first_img = d(className="android.widget.ImageView").instances[i]
                    if first_img.exists:
                        first_img.click()
                        time.sleep(0.3)

        # 선택 완료
        done_btn = d(text="완료") or d(text="선택") or d(description="완료")
        if done_btn.exists(timeout=5):
            done_btn.click()
            time.sleep(1)

    # ─────────────────────────────────────────
    # 게시 메인
    # ─────────────────────────────────────────

    def publish(self, package: ListingPackage) -> PublishResult:
        """당근마켓 앱 게시글 등록"""
        try:
            self._connect()

            # 로그인 확인
            if not self.is_logged_in():
                return PublishResult(
                    platform=Platform.DAANGN,
                    success=False,
                    error_message="당근 앱 로그인 필요. 앱에서 직접 로그인 후 재시도하세요.",
                )

            # 이미지 디바이스에 push
            if package.image_paths:
                self._push_images(package.image_paths)

            # 글쓰기 화면으로 이동
            self._navigate_to_write()
            self._screenshot("write_screen")

            d = self._d

            # ① 이미지 선택
            if package.image_paths:
                logger.info("[당근] 이미지 선택...")
                self._select_images(package.image_paths)

            # ② 제목 입력
            logger.info("[당근] 제목 입력...")
            title_field = (
                d(text="제목") or
                d(hint="제목") or
                d(resourceId=f"{DAANGN_PACKAGE}:id/et_title")
            )
            if title_field.exists(timeout=5):
                title_field.click()
                title_field.clear_text()
                title_field.set_text(package.title)
                time.sleep(0.5)

            # ③ 가격 입력
            logger.info("[당근] 가격 입력...")
            price_field = (
                d(text="₩ 가격 (선택사항)") or
                d(hint="가격") or
                d(resourceId=f"{DAANGN_PACKAGE}:id/et_price")
            )
            if price_field.exists(timeout=3):
                price_field.click()
                price_field.clear_text()
                price_field.set_text(str(package.price))
                time.sleep(0.3)

            # ④ 카테고리 선택
            logger.info("[당근] 카테고리 선택...")
            cat_parts = [p.strip() for p in package.category.split(">")]
            cat_btn = (
                d(text="카테고리 선택") or
                d(resourceId=f"{DAANGN_PACKAGE}:id/tv_category")
            )
            if cat_btn.exists(timeout=3):
                cat_btn.click()
                time.sleep(0.5)
                # 1단계 카테고리
                if cat_parts:
                    d(text=cat_parts[0]).click()
                    time.sleep(0.5)
                # 2단계 카테고리
                if len(cat_parts) > 1:
                    d(text=cat_parts[1]).click()
                    time.sleep(0.5)

            # ⑤ 상품 상태 선택
            logger.info("[당근] 상품 상태 선택...")
            condition_text = CONDITION_MAP[package.condition]
            cond_btn = d(text=condition_text)
            if not cond_btn.exists(timeout=3):
                # "상품 상태" 섹션 찾아서 탭
                d(text="상품 상태").click()
                time.sleep(0.5)
                d(text=condition_text).click()
            else:
                cond_btn.click()
            time.sleep(0.3)

            # ⑥ 내용 입력
            logger.info("[당근] 내용 입력...")
            content_field = (
                d(text="내용을 입력해주세요") or
                d(hint="내용") or
                d(resourceId=f"{DAANGN_PACKAGE}:id/et_content")
            )
            if content_field.exists(timeout=3):
                content_field.click()
                content_field.set_text(package.description)
                time.sleep(0.5)

            self._screenshot("before_submit")

            # ⑦ 완료(등록) 버튼 클릭
            logger.info("[당근] 등록 버튼 클릭...")
            done_btn = (
                d(text="완료") or
                d(text="등록하기") or
                d(description="완료") or
                d(resourceId=f"{DAANGN_PACKAGE}:id/btn_done")
            )
            if not done_btn.exists(timeout=5):
                raise Exception("등록 버튼을 찾지 못함")
            done_btn.click()
            time.sleep(3)

            # ⑧ 성공 확인
            # 등록 후 게시글 상세 화면으로 이동
            success_indicators = [
                d(text="끌어올리기"),   # 게시글 상세에 있는 버튼
                d(text="채팅하기"),
                d(text="수정하기"),
            ]
            if any(ind.exists(timeout=5) for ind in success_indicators):
                self._screenshot("publish_success")
                logger.info("[당근] 게시 완료")
                return PublishResult(
                    platform=Platform.DAANGN,
                    success=True,
                    screenshot_path=self.screenshot_dir / "daangn_publish_success.png",
                )
            else:
                raise Exception("등록 후 상세 화면 확인 실패")

        except Exception as e:
            logger.error(f"[당근] publish 실패: {e}")
            shot = None
            try:
                shot = self._screenshot("publish_error")
            except Exception:
                pass
            return PublishResult(
                platform=Platform.DAANGN,
                success=False,
                error_message=str(e),
                screenshot_path=shot,
            )
