import type { MatchCondition } from "@/model/match";

export function MatchExplanation({ match }: { match: MatchCondition }) {
  const peer = match.peer;
  if (!peer) return null;

  return (
    <section className="match-explanation" aria-label="匹配成立原因">
      <div className="match-person match-person-me">
        <span className="mini-avatar">林</span>
        <div>
          <small>林屿能提供</small>
          <strong>互联网 · 编程</strong>
        </div>
        <p>{match.want_text}</p>
        <span className="want-pill">想学 {match.want_tag}</span>
      </div>

      <div className="covers-board" aria-label="双向覆盖成立">
        <div className="cover-row cover-row-a">
          <span>林屿的互联网能力</span>
          <b>覆盖</b>
          <span>{peer.name} 的产品问题</span>
        </div>
        <div className="cover-row cover-row-b">
          <span>{peer.name} 的训练能力</span>
          <b>覆盖</b>
          <span>林屿的健身问题</span>
        </div>
        <div className="match-result">
          <span aria-hidden="true">✓</span>
          两个条件同时成立
        </div>
      </div>

      <div className="match-person match-person-peer">
        <span className="mini-avatar">周</span>
        <div>
          <small>{peer.name} 能提供</small>
          <strong>{peer.strengths.join(" · ")}</strong>
        </div>
        <p>{peer.want_text}</p>
        <span className="want-pill">想学 {peer.want_tag}</span>
      </div>
    </section>
  );
}
