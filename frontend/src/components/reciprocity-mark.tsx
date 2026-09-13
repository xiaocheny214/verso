export function ReciprocityMark() {
  return (
    <div className="reciprocity-mark" aria-hidden="true">
      <div className="mark-person mark-person-a">
        <span className="person-index">林</span>
        <div>
          <strong>林屿</strong>
          <small>懂产品，也想开始训练</small>
        </div>
      </div>
      <div className="mark-person mark-person-b">
        <span className="person-index">周</span>
        <div>
          <strong>周衡</strong>
          <small>懂训练，也想把经验做成产品</small>
        </div>
      </div>
      <div className="cross-line cross-line-a">
        <span>产品经验</span>
      </div>
      <div className="cross-line cross-line-b">
        <span>训练经验</span>
      </div>
      <div className="mark-want mark-want-a">想补：力量训练</div>
      <div className="mark-want mark-want-b">想补：互联网产品</div>
      <div className="match-seal">
        <span>✓</span>彼此都能回答
      </div>
    </div>
  );
}
