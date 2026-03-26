"""세션 디버그 도구. 사용법: python scripts/debug_session.py [session_id]"""
import sys, json, httpx

BASE = "http://localhost:8000/api/v1"

def main():
    if len(sys.argv) < 2:
        # session_id 없으면 최근 세션 목록 표시
        print("사용법: python scripts/debug_session.py <session_id>")
        print("\n새 세션 생성: python scripts/debug_session.py --new")
        return

    if sys.argv[1] == "--new":
        r = httpx.post(f"{BASE}/sessions")
        d = r.json()
        print(f"새 세션: {d['session_id']} (status: {d['status']})")
        return

    sid = sys.argv[1]
    r = httpx.get(f"{BASE}/sessions/{sid}")
    if r.status_code != 200:
        print(f"에러: {r.status_code} {r.text[:200]}")
        return

    d = r.json()
    print(f"=== 세션 {sid} ===")
    print(f"상태: {d['status']}")
    print(f"에러: {d.get('last_error') or '없음'}")

    if d.get('confirmed_product'):
        cp = d['confirmed_product']
        print(f"상품: {cp.get('brand')} {cp.get('model')} ({cp.get('category')})")

    if d.get('market_context'):
        mc = d['market_context']
        print(f"시세: 중앙값 {mc.get('median_price')}원, 샘플 {mc.get('sample_count')}개")

    if d.get('canonical_listing'):
        cl = d['canonical_listing']
        print(f"판매글: {cl.get('title')}")
        print(f"가격: {cl.get('price')}원")
        print(f"설명: {(cl.get('description') or '')[:100]}...")
    else:
        print("판매글: 없음")

    if d.get('platform_results'):
        for pr in d['platform_results']:
            print(f"게시: {pr.get('platform')} → {'성공' if pr.get('success') else '실패'}")

    print(f"\n전체 JSON:")
    print(json.dumps({k: d[k] for k in ['status', 'canonical_listing', 'market_context', 'last_error', 'confirmed_product']}, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    main()
