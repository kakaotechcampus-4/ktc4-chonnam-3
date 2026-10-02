type FooterProps = {
  /** 오른쪽 안내 문구. 면접 진행 화면은 이탈 경고를 넣는다. */
  note?: string;
};

export default function Footer({ note = '이용약관 · 개인정보처리방침' }: FooterProps) {
  return (
    <footer className="flex items-center border-t border-line-soft px-5 py-2.5 text-[10.5px] text-muted">
      <span>© 2026 DEVON</span>
      <span className="flex-1" />
      <span>{note}</span>
    </footer>
  );
}
