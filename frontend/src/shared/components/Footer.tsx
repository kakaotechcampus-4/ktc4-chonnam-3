type FooterProps = {
  /** 오른쪽 안내 문구. 면접 진행 화면은 이탈 경고를 넣는다. */
  note?: string;
  /** AI 결과를 그대로 믿지 말라는 안내. 있으면 푸터 맨 위에 한 줄로 따로 보여 준다. */
  aiNotice?: string;
};

export default function Footer({ note = '이용약관 · 개인정보처리방침', aiNotice }: FooterProps) {
  return (
    <footer className="border-t border-line-soft px-5 py-2.5 text-[10.5px] text-muted">
      {aiNotice && (
        <p
          role="note"
          className="mb-2 flex items-start justify-center gap-1.5 border-b border-dashed border-line-soft pb-2 text-center"
        >
          <span aria-hidden>⚠</span>
          <span>{aiNotice}</span>
        </p>
      )}
      <div className="flex items-center">
        <span>© 2026 DEVON</span>
        <span className="flex-1" />
        <span>{note}</span>
      </div>
    </footer>
  );
}
