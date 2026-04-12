#!/bin/bash
# 데모 전 체크리스트 — 서버/데이터/권한 자동 검증
# 사용법: bash scripts/demo_check.sh [BASE_URL]

BASE_URL="${1:-http://34.236.36.212}"
PASS=0
FAIL=0

check() {
    local desc="$1"
    local result="$2"
    if [ "$result" = "OK" ]; then
        echo "  [OK] $desc"
        PASS=$((PASS + 1))
    else
        echo "  [FAIL] $desc — $result"
        FAIL=$((FAIL + 1))
    fi
}

echo "=== 사구팔구 데모 체크리스트 ==="
echo "서버: $BASE_URL"
echo ""

# 1. 서버 상태
echo "--- 서버 상태 ---"
HEALTH=$(curl -sf "$BASE_URL/health" 2>/dev/null)
if [ $? -eq 0 ]; then
    check "서버 health" "OK"
else
    check "서버 health" "접속 불가"
fi

# 2. 마켓 상품 수
echo "--- 마켓 데이터 ---"
MARKET=$(curl -sf "$BASE_URL/api/v1/market" 2>/dev/null)
if [ $? -eq 0 ]; then
    TOTAL=$(echo "$MARKET" | python3 -c "import sys,json; print(json.load(sys.stdin).get('total',0))" 2>/dev/null)
    if [ "$TOTAL" -ge 3 ] 2>/dev/null; then
        check "마켓 상품 수 ($TOTAL개)" "OK"
    else
        check "마켓 상품 수 ($TOTAL개)" "3개 이상 필요"
    fi
else
    check "마켓 API" "접속 불가"
fi

# 3. 대시보드 접근 (seller-1)
echo "--- 판매자 대시보드 ---"
MY=$(curl -sf -H "X-Dev-User-Id: seller-1" "$BASE_URL/api/v1/market/my-listings" 2>/dev/null)
if [ $? -eq 0 ]; then
    MY_TOTAL=$(echo "$MY" | python3 -c "import sys,json; print(json.load(sys.stdin).get('total',0))" 2>/dev/null)
    check "대시보드 접근 (seller-1, $MY_TOTAL개)" "OK"
else
    check "대시보드 접근" "실패"
fi

# 4. 권한 차단 (seller-2가 seller-1 접근)
echo "--- 권한 검증 ---"
CROSS=$(curl -sf -o /dev/null -w "%{http_code}" -H "X-Dev-User-Id: seller-2" "$BASE_URL/api/v1/market/my-listings" 2>/dev/null)
if [ "$CROSS" = "200" ]; then
    # seller-2도 200이지만 자기 상품만 보여야 함 (0개)
    CROSS_TOTAL=$(curl -sf -H "X-Dev-User-Id: seller-2" "$BASE_URL/api/v1/market/my-listings" 2>/dev/null | python3 -c "import sys,json; print(json.load(sys.stdin).get('total',0))" 2>/dev/null)
    if [ "$CROSS_TOTAL" = "0" ]; then
        check "seller-2 교차 접근 차단 (0개)" "OK"
    else
        check "seller-2 교차 접근 차단" "seller-2에 $CROSS_TOTAL개 보임"
    fi
else
    check "seller-2 교차 접근" "HTTP $CROSS"
fi

# 5. 마켓 상세 (첫 상품)
echo "--- 마켓 상세 ---"
FIRST_ID=$(echo "$MARKET" | python3 -c "import sys,json; items=json.load(sys.stdin).get('items',[]); print(items[0]['session_id'] if items else '')" 2>/dev/null)
if [ -n "$FIRST_ID" ]; then
    DETAIL=$(curl -sf "$BASE_URL/api/v1/market/$FIRST_ID" 2>/dev/null)
    if [ $? -eq 0 ]; then
        check "상품 상세 ($FIRST_ID)" "OK"
    else
        check "상품 상세" "실패"
    fi
else
    check "상품 상세" "상품 ID 없음"
fi

echo ""
echo "=== 결과: $PASS 통과 / $FAIL 실패 ==="
if [ $FAIL -gt 0 ]; then
    echo "!!! 데모 전 문제 해결 필요 !!!"
    exit 1
else
    echo "데모 준비 완료!"
fi
