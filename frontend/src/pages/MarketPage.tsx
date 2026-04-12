import { useState, useEffect, useCallback, useRef } from "react";
import { api } from "../lib/api";
import type { MarketItem } from "../types/market";
import "./MarketPage.css";

export function MarketPage() {
  const [items, setItems] = useState<MarketItem[]>([]);
  const [, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [showAvailableOnly, setShowAvailableOnly] = useState(true);
  const [selectedCategory, setSelectedCategory] = useState<string>("all");
  const [sortBy, setSortBy] = useState<string>("latest");

  // 검색/필터 상태
  const [query, setQuery] = useState("");
  const [minPrice, setMinPrice] = useState("");
  const [maxPrice, setMaxPrice] = useState("");
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const fetchItems = useCallback(async (q?: string, min?: number, max?: number) => {
    setLoading(true);
    try {
      const hasFilter = (q && q.trim()) || min !== undefined || max !== undefined;
      if (hasFilter) {
        const res = await api.searchMarketItems({
          q: q?.trim() || undefined,
          min_price: min,
          max_price: max,
          limit: 50,
          offset: 0,
        });
        setItems(res.items);
        setTotal(res.total);
      } else {
        const res = await api.getMarketItems(50, 0);
        setItems(res.items);
        setTotal(res.total);
      }
    } catch {
      setItems([]);
      setTotal(0);
    } finally {
      setLoading(false);
    }
  }, []);

  // 초기 로드
  useEffect(() => {
    fetchItems();
  }, [fetchItems]);

  // 디바운스 검색
  const handleSearchChange = (value: string) => {
    setQuery(value);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      const min = minPrice ? parseInt(minPrice, 10) : undefined;
      const max = maxPrice ? parseInt(maxPrice, 10) : undefined;
      fetchItems(value, min, max);
    }, 300);
  };

  const handlePriceFilter = () => {
    const min = minPrice ? parseInt(minPrice, 10) : undefined;
    const max = maxPrice ? parseInt(maxPrice, 10) : undefined;
    fetchItems(query, min, max);
  };

  const handleClearFilters = () => {
    setQuery("");
    setMinPrice("");
    setMaxPrice("");
    fetchItems();
  };

  const hasActiveFilter = query.trim() || minPrice || maxPrice;

  let displayItems = items;
  if (showAvailableOnly) {
    displayItems = displayItems.filter((item) => (item.sale_status || "available") === "available");
  }
  if (selectedCategory !== "all") {
    displayItems = displayItems.filter((item) => (item.category || "") === selectedCategory);
  }
  if (sortBy === "price_asc") {
    displayItems = [...displayItems].sort((a, b) => a.price - b.price);
  } else if (sortBy === "price_desc") {
    displayItems = [...displayItems].sort((a, b) => b.price - a.price);
  }
  const displayTotal = displayItems.length;

  return (
    <div className="market-page">
      <div className="market-header">
        <h1 className="market-title">사구팔구 마켓</h1>
        <div className="market-header__actions">
          <a href="#/my-listings" className="market-my-listings-link">내 상품 관리</a>
          <a href="#/" className="market-back-link">셀러 코파일럿</a>
        </div>
      </div>

      {/* 판매중만 보기 토글 */}
      <div className="market-status-toggle">
        <label className="market-toggle-label">
          <input
            type="checkbox"
            checked={showAvailableOnly}
            onChange={(e) => setShowAvailableOnly(e.target.checked)}
          />
          판매중만 보기
        </label>
      </div>

      {/* 카테고리 필터 */}
      <div className="market-category-filter">
        {["all", "스마트폰", "태블릿", "노트북", "가전", "패션", "기타"].map((cat) => (
          <button
            key={cat}
            className={`market-category-btn ${selectedCategory === cat ? "market-category-btn--active" : ""}`}
            onClick={() => setSelectedCategory(cat)}
          >
            {cat === "all" ? "전체" : cat}
          </button>
        ))}
      </div>

      {/* 정렬 */}
      <div className="market-sort">
        <select className="market-sort-select" value={sortBy} onChange={(e) => setSortBy(e.target.value)}>
          <option value="latest">최신순</option>
          <option value="price_asc">가격 낮은순</option>
          <option value="price_desc">가격 높은순</option>
        </select>
      </div>

      {/* 검색 + 필터 */}
      <div className="market-search-bar">
        <input
          type="text"
          className="market-search-input"
          placeholder="상품명 또는 태그로 검색..."
          value={query}
          onChange={(e) => handleSearchChange(e.target.value)}
        />
        <div className="market-price-filter">
          <input
            type="number"
            className="market-price-input"
            placeholder="최소 가격"
            value={minPrice}
            onChange={(e) => setMinPrice(e.target.value)}
            onBlur={handlePriceFilter}
            onKeyDown={(e) => e.key === "Enter" && handlePriceFilter()}
            min={0}
          />
          <span className="market-price-sep">~</span>
          <input
            type="number"
            className="market-price-input"
            placeholder="최대 가격"
            value={maxPrice}
            onChange={(e) => setMaxPrice(e.target.value)}
            onBlur={handlePriceFilter}
            onKeyDown={(e) => e.key === "Enter" && handlePriceFilter()}
            min={0}
          />
          <button className="market-filter-btn" onClick={handlePriceFilter}>검색</button>
        </div>
      </div>

      {hasActiveFilter && (
        <div className="market-filter-status">
          <span>검색 결과: {displayTotal}개</span>
          <button className="market-clear-btn" onClick={handleClearFilters}>필터 초기화</button>
        </div>
      )}

      {!hasActiveFilter && <p className="market-subtitle">{displayTotal}개 상품</p>}

      {loading ? (
        <div className="market-loading">불러오는 중...</div>
      ) : displayItems.length === 0 ? (
        <div className="market-empty-inline">
          <p>{hasActiveFilter ? "검색 결과가 없습니다." : "등록된 상품이 없습니다."}</p>
        </div>
      ) : (
        <div className="market-grid">
          {displayItems.map((item) => (
            <MarketCard key={item.session_id} item={item} />
          ))}
        </div>
      )}
    </div>
  );
}

function MarketCard({ item }: { item: MarketItem }) {
  const thumbnail = item.image_urls[0] || null;
  const saleStatus = item.sale_status || "available";
  const platformLabel: Record<string, string> = {
    bunjang: "번개장터",
    joongna: "중고나라",
    daangn: "당근마켓",
  };

  return (
    <a href={`#/market/${item.session_id}`} className={`market-card ${saleStatus !== "available" ? "market-card--inactive" : ""}`} style={{ textDecoration: "none" }}>
      <div className="market-card__image-wrapper">
        {thumbnail ? (
          <img className="market-card__image" src={thumbnail} alt={item.title} />
        ) : (
          <div className="market-card__no-image">이미지 없음</div>
        )}
        {saleStatus === "sold" && (
          <div className="market-card__sold-overlay">판매완료</div>
        )}
        {saleStatus === "reserved" && (
          <div className="market-card__reserved-overlay">예약중</div>
        )}
      </div>
      <div className="market-card__body">
        <h3 className="market-card__title">{item.title || "제목 없음"}</h3>
        <p className="market-card__price">{item.price.toLocaleString()}원</p>
        {item.published_platforms.length > 0 && (
          <div className="market-card__platforms">
            {item.published_platforms.map((p) => (
              <span key={p} className="market-card__platform-badge">
                {platformLabel[p] || p}
              </span>
            ))}
          </div>
        )}
        {item.tags.length > 0 && (
          <div className="market-card__tags">
            {item.tags.slice(0, 3).map((tag) => (
              <span key={tag} className="market-card__tag">#{tag}</span>
            ))}
          </div>
        )}
      </div>
    </a>
  );
}
