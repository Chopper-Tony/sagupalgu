"""InquiryRepository — 마켓 구매 문의 CRUD.

inquiries 테이블에 대한 DB 접근. Supabase PostgREST 사용.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


class InquiryRepository:
    table_name = "inquiries"

    def create(
        self,
        listing_id: str,
        buyer_name: str,
        buyer_contact: str,
        message: str,
    ) -> dict[str, Any]:
        """새 문의를 생성한다."""
        from app.db.client import get_supabase

        record = {
            "id": str(uuid4()),
            "listing_id": listing_id,
            "buyer_name": buyer_name,
            "buyer_contact": buyer_contact,
            "message": message,
            "status": "open",
            "is_read": False,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        response = get_supabase().table(self.table_name).insert(record).execute()
        return response.data[0] if response.data else record

    def list_by_listing(self, listing_id: str) -> list[dict[str, Any]]:
        """특정 상품의 문의 목록을 조회한다 (최신순)."""
        from app.db.client import get_supabase

        response = (
            get_supabase()
            .table(self.table_name)
            .select("*")
            .eq("listing_id", listing_id)
            .order("created_at", desc=True)
            .execute()
        )
        return response.data or []

    def get_by_id(self, inquiry_id: str) -> dict[str, Any] | None:
        """문의 단건 조회."""
        from app.db.client import get_supabase

        response = (
            get_supabase()
            .table(self.table_name)
            .select("*")
            .eq("id", inquiry_id)
            .limit(1)
            .execute()
        )
        data = response.data or []
        return data[0] if data else None

    def reply(self, inquiry_id: str, reply_text: str) -> dict[str, Any] | None:
        """판매자 응답을 저장한다. 상태를 replied로 자동 전이."""
        from app.db.client import get_supabase

        now = datetime.now(timezone.utc).isoformat()
        payload = {
            "reply": reply_text,
            "status": "replied",
            "is_read": True,
            "last_reply_at": now,
        }
        response = (
            get_supabase()
            .table(self.table_name)
            .update(payload)
            .eq("id", inquiry_id)
            .execute()
        )
        return response.data[0] if response.data else None

    def mark_read(self, inquiry_id: str) -> None:
        """문의를 읽음 처리한다."""
        from app.db.client import get_supabase

        get_supabase().table(self.table_name).update(
            {"is_read": True}
        ).eq("id", inquiry_id).execute()

    def count_unread(self, listing_id: str) -> int:
        """특정 상품의 읽지 않은 문의 수를 반환한다."""
        from app.db.client import get_supabase

        response = (
            get_supabase()
            .table(self.table_name)
            .select("id", count="exact")
            .eq("listing_id", listing_id)
            .eq("is_read", False)
            .execute()
        )
        return response.count or 0

    def count_by_listing(self, listing_id: str) -> int:
        """특정 상품의 총 문의 수를 반환한다."""
        from app.db.client import get_supabase

        response = (
            get_supabase()
            .table(self.table_name)
            .select("id", count="exact")
            .eq("listing_id", listing_id)
            .execute()
        )
        return response.count or 0
