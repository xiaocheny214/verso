export function ReciprocityMark() {
  return (
    <div className="reciprocity-mark" aria-hidden="true">
      <div className="mark-person mark-person-a">
        <span className="person-index">A</span>
        <strong>互联网产品</strong>
        <small>我能教</small>
      </div>
      <div className="mark-person mark-person-b">
        <span className="person-index">B</span>
        <strong>力量训练</strong>
        <small>我能教</small>
      </div>
      <div className="cross-line cross-line-a">
        <span>A 的能力</span>
      </div>
      <div className="cross-line cross-line-b">
        <span>B 的能力</span>
      </div>
      <div className="mark-want mark-want-a">想学训练</div>
      <div className="mark-want mark-want-b">想做产品</div>
      <div className="match-seal">双向成立</div>
    </div>
  );
}
