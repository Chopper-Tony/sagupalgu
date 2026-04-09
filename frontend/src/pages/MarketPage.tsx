import { useState, useEffect } from "react";
import { api } from "../lib/api";
import type { MarketItem } from "../types/market";
import "./MarketPage.css";

export function MarketPage() {
  const [items, setItems] = useState<MarketItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api
      .getMarketItems(20, 0)
      .then((res) => setItems(res.items))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="market-loading">불러오는 중...</div>;
  if (items.length === 0) return (
    <div className="market-empty">
      <p className="market-empty__title">사구팔구 마켓</p>
      <p className="market-empty__sub">등록된 상품이 없습니다.</p>
      <a href="#/" className="market-empty__link">셀러 코파일럿으로 돌아가기</a>
    </div>
  );

  return (
    <div className="market-page">
      <div className="market-header">
        <h1 className="market-title">사구팔구 마켓</h1>
        <a href="#/" className="market-back-link">셀러 코파일럿</a>
      </div>
      <p className="market-subtitle">{items.length}개 상품</p>
      <div className="market-grid">
        {items.map((item) => (
          <MarketCard key={item.session_id} item={item} />
        ))}
      </div>
    </div>
  );
}

function MarketCard({ item }: { item: MarketItem }) {
  const thumbnail = item.image_urls[0] || null;
  const platformLabel: Record<string, string> = {
    bunjang: "번개장터",
    joongna: "중고나라",
    daangn: "당근마켓",
  };

  return (
    <div className="market-card">
      {thumbnail ? (
        <img className="market-card__image" src={thumbnail} alt={item.title} />
      ) : (
        <div className="market-card__no-image">이미지 없음</div>
      )}
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
    </div>
  );
}
