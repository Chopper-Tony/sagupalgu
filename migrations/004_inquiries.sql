-- 004_inquiries.sql
-- 마켓 구매 문의 테이블.
-- 문의 → 응답 → 상태 관리, 셀러 코파일럿(SC-3) 연동 기반.

CREATE TABLE IF NOT EXISTS inquiries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    listing_id UUID NOT NULL,                        -- sell_sessions.id 참조
    buyer_name TEXT NOT NULL,
    buyer_contact TEXT NOT NULL,
    message TEXT NOT NULL,
    reply TEXT,
    status TEXT NOT NULL DEFAULT 'open',              -- open / replied / closed
    is_read BOOLEAN NOT NULL DEFAULT FALSE,
    last_reply_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_inquiries_listing ON inquiries(listing_id);
CREATE INDEX IF NOT EXISTS idx_inquiries_status ON inquiries(status);
CREATE INDEX IF NOT EXISTS idx_inquiries_is_read ON inquiries(listing_id, is_read) WHERE NOT is_read;
