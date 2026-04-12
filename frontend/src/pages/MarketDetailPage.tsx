import { useState, useEffect } from "react";
import { api } from "../lib/api";
import type { MarketDetailItem } from "../types/market";
import "./MarketDetailPage.css";

const PLATFORM_LABEL: Record<string, string> = {
  bunjang: "번개장터",
  joongna: "중고나라",
  daangn: "당근마켓",
};

interface Props {
  sessionId: string;
}

export function MarketDetailPage({ sessionId }: Props) {
  const [item, setItem] = useState<MarketDetailItem | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // 문의 폼 상태
  const [showInquiry, setShowInquiry] = useState(false);
  const [inquiryName, setInquiryName] = useState("");
  const [inquiryContact, setInquiryContact] = useState("");
  const [inquiryMessage, setInquiryMessage] = useState("");
  const [inquirySending, setInquirySending] = useState(false);
  const [inquiryDone, setInquiryDone] = useState(false);

  useEffect(() => {
    setLoading(true);
    setError(null);
    api
      .getMarketItem(sessionId)
      .then((data) => setItem(data))
      .catch(() => setError("상품을 찾을 수 없습니다."))
      .finally(() => setLoading(false));
  }, [sessionId]);

  const handleSubmitInquiry = async () => {
    if (!inquiryName.trim() || !inquiryContact.trim() || !inquiryMessage.trim()) return;
    setInquirySending(true);
    try {
      await api.submitInquiry(sessionId, {
        name: inquiryName.trim(),
        contact: inquiryContact.trim(),
        message: inquiryMessage.trim(),
      });
      setInquiryDone(true);
    } catch {
      setError("문의 전송에 실패했습니다. 다시 시도해주세요.");
    } finally {
      setInquirySending(false);
    }
  };

  if (loading) return <div className="detail-loading">불러오는 중...</div>;
  if (error || !item) {
    return (
      <div className="detail-error">
        <p>{error || "상품을 찾을 수 없습니다."}</p>
        <a href="#/market" className="detail-back-link">목록으로 돌아가기</a>
      </div>
    );
  }

  return (
    <div className="detail-page">
      <a href="#/market" className="detail-back-link">목록으로 돌아가기</a>

      {/* 이미지 갤러리 */}
      {item.image_urls.length > 0 && (
        <div className="detail-gallery">
          {item.image_urls.map((url, i) => (
            <img key={i} className="detail-gallery__img" src={url} alt={`${item.title} ${i + 1}`} />
          ))}
        </div>
      )}

      {/* 제목 + 가격 + 판매 상태 */}
      <div className="detail-title-row">
        <h1 className="detail-title">{item.title || "제목 없음"}</h1>
        {item.sale_status === "sold" && <span className="detail-status-badge detail-status-badge--sold">판매완료</span>}
        {item.sale_status === "reserved" && <span className="detail-status-badge detail-status-badge--reserved">예약중</span>}
      </div>
      <p className="detail-price">{item.price.toLocaleString()}원</p>

      {/* 태그 */}
      {item.tags.length > 0 && (
        <div className="detail-tags">
          {item.tags.map((tag) => (
            <span key={tag} className="detail-tag">#{tag}</span>
          ))}
        </div>
      )}

      {/* 설명 */}
      <div className="detail-description">
        {item.description.split("\n").map((line, i) => (
          <p key={i}>{line}</p>
        ))}
      </div>

      {/* 게시 플랫폼 링크 */}
      {item.platform_links.length > 0 && (
        <div className="detail-platforms">
          <h3 className="detail-section-title">게시된 플랫폼</h3>
          <div className="detail-platform-links">
            {item.platform_links.map((link) => (
              <a
                key={link.platform}
                href={link.url || "#"}
                target="_blank"
                rel="noopener noreferrer"
                className={`detail-platform-link ${link.url ? "" : "detail-platform-link--no-url"}`}
              >
                {PLATFORM_LABEL[link.platform] || link.platform}
                {link.url && <span className="detail-platform-link__arrow">&rarr;</span>}
              </a>
            ))}
          </div>
        </div>
      )}

      {/* 구매 문의 — 판매완료/예약중이면 비활성화 */}
      <div className="detail-inquiry-section">
        {item.sale_status === "sold" && (
          <p className="detail-inquiry-unavailable">이미 판매가 완료된 상품입니다.</p>
        )}
        {item.sale_status === "reserved" && (
          <p className="detail-inquiry-unavailable">현재 예약 중인 상품입니다.</p>
        )}
        {(!item.sale_status || item.sale_status === "available") && !showInquiry && !inquiryDone && (
          <button className="detail-inquiry-btn" onClick={() => setShowInquiry(true)}>
            판매자에게 문의
          </button>
        )}

        {showInquiry && !inquiryDone && (
          <div className="detail-inquiry-form">
            <h3 className="detail-section-title">구매 문의</h3>
            <input
              type="text"
              className="detail-inquiry-input"
              placeholder="이름"
              value={inquiryName}
              onChange={(e) => setInquiryName(e.target.value)}
              maxLength={50}
            />
            <input
              type="text"
              className="detail-inquiry-input"
              placeholder="연락처 (전화번호 또는 이메일)"
              value={inquiryContact}
              onChange={(e) => setInquiryContact(e.target.value)}
              maxLength={100}
            />
            <textarea
              className="detail-inquiry-textarea"
              placeholder="문의 내용을 입력해주세요"
              value={inquiryMessage}
              onChange={(e) => setInquiryMessage(e.target.value)}
              maxLength={1000}
              rows={4}
            />
            <div className="detail-inquiry-actions">
              <button
                className="detail-inquiry-submit"
                onClick={handleSubmitInquiry}
                disabled={inquirySending || !inquiryName.trim() || !inquiryContact.trim() || !inquiryMessage.trim()}
              >
                {inquirySending ? "전송 중..." : "문의 보내기"}
              </button>
              <button className="detail-inquiry-cancel" onClick={() => setShowInquiry(false)}>
                취소
              </button>
            </div>
          </div>
        )}

        {inquiryDone && (
          <div className="detail-inquiry-done">
            문의가 전송되었습니다. 판매자가 확인 후 연락드리겠습니다.
          </div>
        )}
      </div>

      {/* 등록일 */}
      {item.created_at && (
        <p className="detail-created-at">
          등록일: {new Date(item.created_at).toLocaleDateString("ko-KR")}
        </p>
      )}
    </div>
  );
}
