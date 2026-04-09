import { useState, useRef, useCallback } from "react";
import type { ComposerMode } from "../../types";
import "./ChatComposer.css";

interface ChatComposerProps {
  mode: ComposerMode;
  onSendText: (text: string) => void;
  onUploadImages: (files: File[]) => void;
}

const PLACEHOLDER: Record<ComposerMode, string> = {
  upload: "사진을 업로드하거나 메시지를 입력하세요",
  confirmation: "브랜드, 모델명, 카테고리를 입력하세요 (예: Apple iPhone 15 Pro 스마트폰)",
  rewrite: "재작성 지시사항을 입력하세요 (예: 더 신뢰감 있게 작성해주세요)",
  disabled: "AI가 처리 중입니다...",
};

export function ChatComposer({ mode, onSendText, onUploadImages }: ChatComposerProps) {
  const [text, setText] = useState("");
  const fileInputRef = useRef<HTMLInputElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const autoResize = useCallback(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = el.scrollHeight + "px";
  }, []);

  const handleSubmit = () => {
    const trimmed = text.trim();
    if (!trimmed || mode === "disabled") return;
    onSendText(trimmed);
    setText("");
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files ?? []);
    if (files.length > 0) onUploadImages(files);
    e.target.value = "";
  };

  if (mode === "disabled") {
    return (
      <div className="chat-composer chat-composer--disabled">
        <textarea
          className="chat-composer__input"
          placeholder={PLACEHOLDER[mode]}
          disabled
          rows={1}
        />
      </div>
    );
  }

  return (
    <div className="chat-composer">
      {mode === "upload" && (
        <>
          <button
            className="chat-composer__upload-btn"
            onClick={() => fileInputRef.current?.click()}
            title="이미지 업로드"
          >
            📷
          </button>
          <input
            ref={fileInputRef}
            type="file"
            accept="image/*"
            multiple
            style={{ display: "none" }}
            onChange={handleFileChange}
          />
        </>
      )}
      <textarea
        ref={textareaRef}
        className="chat-composer__input"
        value={text}
        onChange={(e) => setText(e.target.value)}
        onInput={autoResize}
        onKeyDown={handleKeyDown}
        placeholder={PLACEHOLDER[mode]}
        rows={1}
        style={{ maxHeight: 200, overflowY: "auto" }}
      />
      <button
        className="chat-composer__send-btn"
        onClick={handleSubmit}
        disabled={!text.trim()}
      >
        ↑
      </button>
    </div>
  );
}
