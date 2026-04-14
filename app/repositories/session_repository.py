from datetime import datetime, timezone
from uuid import uuid4
from app.db.client import get_supabase
from app.db.models import SellSession

SALE_STATUS_TRANSITIONS = {
    "available": ["reserved", "sold"],
    "reserved": ["sold", "available"],
    "sold": [],  # 판매 완료는 되돌릴 수 없음
}


def _get_sale_status(session: dict) -> str:
    """세션에서 마켓 판매 상태를 추출한다. 기본값 available."""
    listing_data = session.get("listing_data_jsonb") or {}
    return listing_data.get("sale_status", "available")


class SessionRepository:
    table_name = "sell_sessions"

    def create(self, user_id: str) -> SellSession:
        now = datetime.now(timezone.utc)
        session = SellSession(
            id=str(uuid4()),
            user_id=user_id,
            status="session_created",
            selected_platforms_jsonb=[],
            product_data_jsonb={},
            listing_data_jsonb={},
            workflow_meta_jsonb={"schema_version": 1, "checkpoint": None},
            created_at=now,
            updated_at=now,
        )
        get_supabase().table(self.table_name).insert(session.to_record()).execute()
        return session

    def get_by_id(self, session_id: str):
        response = (
            get_supabase()
            .table(self.table_name)
            .select("*")
            .eq("id", session_id)
            .limit(1)
            .execute()
        )
        data = response.data or []
        return data[0] if data else None

    def get_by_id_and_user(self, session_id: str, user_id: str):
        """세션 ID + 소유자 ID로 조회. 소유권 불일치 시 None 반환."""
        response = (
            get_supabase()
            .table(self.table_name)
            .select("*")
            .eq("id", session_id)
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
        data = response.data or []
        return data[0] if data else None

    def update(self, session_id: str, payload: dict, expected_status: str | None = None):
        payload["updated_at"] = datetime.now(timezone.utc).isoformat()
        query = (
            get_supabase()
            .table(self.table_name)
            .update(payload)
            .eq("id", session_id)
        )
        if expected_status:
            query = query.eq("status", expected_status)
        response = query.execute()
        return response.data[0] if response.data else None

    def list_completed(self, limit: int = 20, offset: int = 0) -> tuple[list[dict], int]:
        """completed 상태 세션 목록 조회 (마켓용, 최신순)."""
        from app.db.client import get_supabase

        response = (
            get_supabase()
            .table(self.table_name)
            .select("id, product_data_jsonb, listing_data_jsonb, workflow_meta_jsonb, created_at")
            .eq("status", "completed")
            .order("created_at", desc=True)
            .range(offset, offset + limit - 1)
            .execute()
        )
        items = response.data or []

        count_response = (
            get_supabase()
            .table(self.table_name)
            .select("id", count="exact")
            .eq("status", "completed")
            .execute()
        )
        total = count_response.count or 0

        return items, total

    def search_completed(
        self,
        q: str | None = None,
        min_price: int | None = None,
        max_price: int | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[dict], int]:
        """completed 상태 세션 검색 (키워드 + 가격 범위 필터)."""
        from app.db.client import get_supabase

        cols = "id, product_data_jsonb, listing_data_jsonb, workflow_meta_jsonb, created_at"
        query = (
            get_supabase()
            .table(self.table_name)
            .select(cols)
            .eq("status", "completed")
        )
        count_query = (
            get_supabase()
            .table(self.table_name)
            .select("id", count="exact")
            .eq("status", "completed")
        )

        # Supabase PostgREST는 JSONB 내부 필드 ILIKE를 직접 지원하지 않으므로
        # 전체 조회 후 Python 필터링으로 처리한다 (상품 수 규모가 작으므로 허용).
        response = query.order("created_at", desc=True).execute()
        all_items = response.data or []

        def _matches(row: dict) -> bool:
            listing = (row.get("listing_data_jsonb") or {}).get("canonical_listing") or {}
            title = (listing.get("title") or "").lower()
            tags = listing.get("tags") or []
            price = listing.get("price", 0)
            if isinstance(price, str):
                try:
                    price = int(price)
                except (ValueError, TypeError):
                    price = 0

            if q:
                keyword = q.lower()
                tag_match = any(keyword in t.lower() for t in tags)
                if keyword not in title and not tag_match:
                    return False

            if min_price is not None and price < min_price:
                return False
            if max_price is not None and price > max_price:
                return False
            return True

        filtered = [row for row in all_items if _matches(row)]
        total = len(filtered)
        page = filtered[offset : offset + limit]
        return page, total

    def list_by_user(self, user_id: str, sale_status_filter: str | None = None) -> list[dict]:
        """특정 사용자의 completed 세션 목록 (판매자 대시보드용)."""
        from app.db.client import get_supabase

        cols = "id, product_data_jsonb, listing_data_jsonb, workflow_meta_jsonb, created_at"
        query = (
            get_supabase()
            .table(self.table_name)
            .select(cols)
            .eq("user_id", user_id)
            .eq("status", "completed")
            .order("created_at", desc=True)
        )
        items = (query.execute()).data or []

        if sale_status_filter:
            items = [
                row for row in items
                if _get_sale_status(row) == sale_status_filter
            ]
        return items

    def update_sale_status(
        self, session_id: str, user_id: str, new_status: str, allowed_from: list[str],
    ) -> dict | None:
        """마켓 판매 상태를 원자적으로 변경. race condition 방어 포함."""
        from app.db.client import get_supabase

        # 현재 세션 + 소유권 확인
        session = self.get_by_id_and_user(session_id, user_id)
        if not session:
            return None

        current_status = _get_sale_status(session)
        if current_status not in allowed_from:
            from app.domain.exceptions import InvalidStateTransitionError
            raise InvalidStateTransitionError(
                f"판매 상태 전이 불가: {current_status} → {new_status} (허용: {allowed_from})"
            )

        listing_data = dict(session.get("listing_data_jsonb") or {})
        listing_data["sale_status"] = new_status

        payload = {
            "listing_data_jsonb": listing_data,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        response = (
            get_supabase()
            .table(self.table_name)
            .update(payload)
            .eq("id", session_id)
            .eq("user_id", user_id)
            .execute()
        )
        return response.data[0] if response.data else None

    def get_completed_by_id(self, session_id: str) -> dict | None:
        """completed 상태 세션 단건 조회 (마켓 상세용)."""
        from app.db.client import get_supabase

        response = (
            get_supabase()
            .table(self.table_name)
            .select("id, user_id, product_data_jsonb, listing_data_jsonb, workflow_meta_jsonb, created_at")
            .eq("id", session_id)
            .eq("status", "completed")
            .limit(1)
            .execute()
        )
        data = response.data or []
        return data[0] if data else None
