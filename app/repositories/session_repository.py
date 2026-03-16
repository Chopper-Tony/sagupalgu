from datetime import datetime, timezone
from uuid import uuid4
from app.db.client import get_supabase
from app.db.models import SellSession

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

    def update(self, session_id: str, payload: dict):
        payload["updated_at"] = datetime.now(timezone.utc).isoformat()
        response = (
            get_supabase()
            .table(self.table_name)
            .update(payload)
            .eq("id", session_id)
            .execute()
        )
        return response.data[0] if response.data else None
