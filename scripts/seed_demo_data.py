#!/usr/bin/env python3
"""
데모 시드 데이터 생성 스크립트.

Idempotent: --reset 시 기존 데모 데이터 삭제 후 재생성.
Deterministic: 랜덤 없이 고정 상품 세트.
듀얼 모드: --mode api (dev bypass) / --mode db (직접 DB insert).

사용법:
    python scripts/seed_demo_data.py --base-url http://34.236.36.212
    python scripts/seed_demo_data.py --reset --base-url http://34.236.36.212
    python scripts/seed_demo_data.py --mode db
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone

DEMO_USER = "seller-1"
DEMO_TAG = "demo-seed"

# ── 고정 데이터 세트 ──────────────────────────────────

PRODUCTS = [
    {
        "title": "아이폰 15 프로 256GB",
        "description": "깨끗하게 사용한 아이폰 15 프로입니다.\n256GB 블랙 티타늄, 배터리 93%.\n풀박스 구성 (본체+충전기+케이스).\n직거래 서울 강남역 선호합니다.",
        "price": 980000,
        "category": "스마트폰",
        "tags": ["아이폰", "아이폰15프로", "256GB", "블랙티타늄"],
        "sale_status": "available",
        "days_ago": 5,
        "inquiries": [
            {"name": "김구매", "contact": "010-1234-5678", "message": "네고 가능하세요? 90만원에 살 수 있을까요?"},
            {"name": "이관심", "contact": "buyer@email.com", "message": "배터리 상태 어떤가요? 하자 있나요?", "reply": "배터리 93%이고 하자 없습니다!"},
        ],
    },
    {
        "title": "맥북 에어 M2 13인치 512GB",
        "description": "2023년 구매한 맥북 에어 M2입니다.\n미드나이트 512GB, 충전 사이클 47회.\nAppleCare+ 2024년 12월까지.\n박스+어댑터+USB-C 케이블 포함.",
        "price": 1150000,
        "category": "노트북",
        "tags": ["맥북", "맥북에어", "M2", "512GB"],
        "sale_status": "available",
        "days_ago": 8,
        "inquiries": [],
    },
    {
        "title": "에어팟 프로 2세대 USB-C",
        "description": "에어팟 프로 2세대 USB-C 모델입니다.\n거의 새것, 한 달 사용.\n노이즈캔슬링 정상 작동.\n케이스 포함.",
        "price": 230000,
        "category": "가전",
        "tags": ["에어팟", "에어팟프로", "USB-C", "노이즈캔슬링"],
        "sale_status": "reserved",
        "days_ago": 3,
        "inquiries": [
            {"name": "박예약", "contact": "010-9876-5432", "message": "내일 직거래 가능하세요?"},
        ],
    },
    {
        "title": "갤럭시 탭 S9 Wi-Fi 128GB",
        "description": "갤럭시 탭 S9 Wi-Fi 모델입니다.\n128GB 그라파이트, S펜 포함.\n화면 보호 필름 부착 상태.\n택배 거래 가능합니다.",
        "price": 520000,
        "category": "태블릿",
        "tags": ["갤럭시탭", "갤럭시탭S9", "S펜", "태블릿"],
        "sale_status": "sold",
        "days_ago": 15,
        "inquiries": [
            {"name": "최구매", "contact": "010-5555-1234", "message": "구매 완료했습니다. 감사합니다!", "reply": "감사합니다! 좋은 거래였습니다."},
        ],
    },
]


def seed_via_api(base_url: str, reset: bool):
    """API 호출로 시드 데이터 생성."""
    import httpx

    headers = {"X-Dev-User-Id": DEMO_USER}
    client = httpx.Client(base_url=base_url, headers=headers, timeout=30.0)

    if reset:
        print("[RESET] 기존 데모 데이터 정리 중...")
        try:
            resp = client.get("/api/v1/market/my-listings")
            if resp.status_code == 200:
                items = resp.json().get("items", [])
                print(f"  기존 상품 {len(items)}개 발견 (정리는 수동 또는 DB 모드 사용)")
        except Exception as e:
            print(f"  정리 실패 (무시): {e}")

    print(f"\n[SEED] {len(PRODUCTS)}개 상품 생성 시작...\n")

    for i, product in enumerate(PRODUCTS, 1):
        print(f"--- 상품 {i}: {product['title']} ---")

        # 1. 세션 생성
        resp = client.post("/api/v1/sessions")
        if resp.status_code != 200:
            print(f"  [ERROR] 세션 생성 실패: {resp.status_code}")
            continue
        session_id = resp.json().get("session_id")
        print(f"  세션: {session_id}")

        # 2. 직접 DB 업데이트 (completed 상태로 세팅)
        # API 모드에서는 listing_data를 직접 설정할 수 없으므로
        # update-listing API를 사용하거나, 최소한의 파이프라인을 실행
        # 여기서는 간소화를 위해 Supabase를 통한 직접 업데이트 사용
        _direct_update_session(session_id, product)
        print(f"  상태: {product['sale_status']}")

        # 3. 문의 생성
        for inq in product.get("inquiries", []):
            try:
                inq_resp = client.post(f"/api/v1/market/{session_id}/inquiry", json={
                    "name": inq["name"],
                    "contact": inq["contact"],
                    "message": inq["message"],
                })
                if inq_resp.status_code == 200:
                    inquiry_id = inq_resp.json().get("inquiry_id")
                    print(f"  문의 생성: {inq['name']} → {inq['message'][:30]}...")

                    # 답변이 있으면 reply
                    if inq.get("reply") and inquiry_id:
                        reply_resp = client.post(
                            f"/api/v1/market/my-listings/{session_id}/inquiries/{inquiry_id}/reply",
                            json={"reply": inq["reply"]},
                        )
                        if reply_resp.status_code == 200:
                            print(f"  답변 완료: {inq['reply'][:30]}...")
                else:
                    print(f"  [WARN] 문의 생성 실패: {inq_resp.status_code} {inq_resp.text[:100]}")
            except Exception as e:
                print(f"  [WARN] 문의 생성 에러: {e}")

        print()

    print("[DONE] 시드 데이터 생성 완료!")
    print(f"  마켓: {base_url}/#/market")
    print(f"  대시보드: {base_url}/#/my-listings")


def _direct_update_session(session_id: str, product: dict):
    """Supabase를 통해 세션을 직접 completed 상태로 업데이트."""
    try:
        from app.db.client import get_supabase

        now = datetime.now(timezone.utc)
        created_at = (now - timedelta(days=product["days_ago"])).isoformat()

        listing_data = {
            "canonical_listing": {
                "title": product["title"],
                "description": product["description"],
                "price": product["price"],
                "tags": product["tags"],
            },
            "sale_status": product["sale_status"],
        }

        product_data = {
            "confirmed_product": {
                "category": product["category"],
                "brand": product["title"].split()[0],
                "model": product["title"],
            },
            "image_paths": ["/uploads/demo-placeholder.jpg"],
        }

        workflow_meta = {
            "schema_version": 1,
            "demo_seed": True,
            "demo_tag": DEMO_TAG,
        }

        payload = {
            "status": "completed",
            "listing_data_jsonb": listing_data,
            "product_data_jsonb": product_data,
            "workflow_meta_jsonb": workflow_meta,
            "created_at": created_at,
            "updated_at": now.isoformat(),
        }

        get_supabase().table("sell_sessions").update(payload).eq("id", session_id).execute()

    except Exception as e:
        print(f"  [ERROR] DB 업데이트 실패: {e}")


def seed_via_db(reset: bool):
    """직접 DB insert로 시드 데이터 생성 (발표 직전 안정용)."""
    try:
        from uuid import uuid4
        from app.db.client import get_supabase

        supabase = get_supabase()

        if reset:
            print("[RESET] demo_seed 태그 데이터 삭제 중...")
            # workflow_meta에 demo_seed: true인 세션 찾아서 삭제
            resp = supabase.table("sell_sessions").select("id, workflow_meta_jsonb").eq("user_id", DEMO_USER).execute()
            demo_ids = [
                r["id"] for r in (resp.data or [])
                if (r.get("workflow_meta_jsonb") or {}).get("demo_seed")
            ]
            if demo_ids:
                for did in demo_ids:
                    supabase.table("inquiries").delete().eq("listing_id", did).execute()
                    supabase.table("sell_sessions").delete().eq("id", did).execute()
                print(f"  {len(demo_ids)}개 세션 + 관련 문의 삭제 완료")

        print(f"\n[SEED] DB 직접 모드 — {len(PRODUCTS)}개 상품 생성\n")

        now = datetime.now(timezone.utc)

        for i, product in enumerate(PRODUCTS, 1):
            session_id = str(uuid4())
            created_at = (now - timedelta(days=product["days_ago"])).isoformat()

            record = {
                "id": session_id,
                "user_id": DEMO_USER,
                "status": "completed",
                "listing_data_jsonb": {
                    "canonical_listing": {
                        "title": product["title"],
                        "description": product["description"],
                        "price": product["price"],
                        "tags": product["tags"],
                    },
                    "sale_status": product["sale_status"],
                },
                "product_data_jsonb": {
                    "confirmed_product": {"category": product["category"]},
                    "image_paths": ["/uploads/demo-placeholder.jpg"],
                },
                "workflow_meta_jsonb": {"schema_version": 1, "demo_seed": True, "demo_tag": DEMO_TAG},
                "selected_platforms_jsonb": [],
                "created_at": created_at,
                "updated_at": now.isoformat(),
            }

            supabase.table("sell_sessions").insert(record).execute()
            print(f"  상품 {i}: {product['title']} ({product['sale_status']})")

            # 문의 생성
            for inq in product.get("inquiries", []):
                inq_record = {
                    "id": str(uuid4()),
                    "listing_id": session_id,
                    "buyer_name": inq["name"],
                    "buyer_contact": inq["contact"],
                    "message": inq["message"],
                    "reply": inq.get("reply"),
                    "status": "replied" if inq.get("reply") else "open",
                    "is_read": bool(inq.get("reply")),
                    "last_reply_at": now.isoformat() if inq.get("reply") else None,
                    "created_at": created_at,
                }
                supabase.table("inquiries").insert(inq_record).execute()
                print(f"    문의: {inq['name']} {'(답변 완료)' if inq.get('reply') else '(대기 중)'}")

        print("\n[DONE] DB 시드 완료!")

    except Exception as e:
        print(f"[ERROR] DB 시드 실패: {e}")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="사구팔구 데모 시드 데이터 생성")
    parser.add_argument("--base-url", default="http://localhost:8000", help="API 서버 URL")
    parser.add_argument("--mode", choices=["api", "db"], default="api", help="생성 모드 (api: HTTP 호출, db: 직접 DB)")
    parser.add_argument("--reset", action="store_true", help="기존 데모 데이터 삭제 후 재생성")
    args = parser.parse_args()

    if args.mode == "api":
        seed_via_api(args.base_url, args.reset)
    else:
        seed_via_db(args.reset)


if __name__ == "__main__":
    main()
