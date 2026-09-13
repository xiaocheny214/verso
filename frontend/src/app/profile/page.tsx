import Link from "next/link";

import { AppFrame } from "@/components/app-frame";
import { demoUser } from "@/lib/demo-data";

const sourceLabels = {
  contents: "知乎创作",
  favorites: "知乎收藏",
  self_reported: "本人补充",
} as const;

export default function ProfilePage() {
  const stable = demoUser.portraits.find(
    (portrait) => portrait.horizon === "stable",
  );
  const recent = demoUser.portraits.find(
    (portrait) => portrait.horizon === "recent_7d",
  );

  return (
    <AppFrame active="画像">
      <main className="profile-layout">
        <section className="profile-heading">
          <div className="avatar-mark" aria-hidden="true">
            林
          </div>
          <div>
            <p className="context-line">知乎身份已认证 · 刚刚同步</p>
            <h1>{demoUser.name} 的能力背叶</h1>
            <p>
              画像只回答“你能提供什么”。这次想学的内容将在匹配时单独填写，不会污染长期画像。
            </p>
          </div>
          <button className="quiet-button" type="button">
            重新同步知乎
          </button>
        </section>

        <div className="portrait-ledger">
          <section className="portrait-column" aria-labelledby="stable-title">
            <header>
              <span>长期画像</span>
              <h2 id="stable-title">反复出现的能力</h2>
              <p>来自公开创作与收藏，适合用于稳定匹配。</p>
            </header>
            <div className="evidence-list">
              {stable?.strengths.map((strength) => (
                <article
                  className="evidence-row"
                  key={`${strength.tag}-${strength.evidence_title}`}
                >
                  <strong>{strength.tag}</strong>
                  <div>
                    <span>{sourceLabels[strength.source]}</span>
                    <p>{strength.evidence_title}</p>
                  </div>
                </article>
              ))}
            </div>
          </section>

          <section
            className="portrait-column recent-column"
            aria-labelledby="recent-title"
          >
            <header>
              <span>近 7 天</span>
              <h2 id="recent-title">最近正在投入</h2>
              <p>让刚形成的能力也有机会参与这次匹配。</p>
            </header>
            <div className="evidence-list">
              {recent?.strengths.map((strength) => (
                <article
                  className="evidence-row"
                  key={`${strength.tag}-${strength.evidence_title}`}
                >
                  <strong>{strength.tag}</strong>
                  <div>
                    <span>{sourceLabels[strength.source]}</span>
                    <p>{strength.evidence_title}</p>
                  </div>
                </article>
              ))}
            </div>
          </section>
        </div>

        <footer className="page-next">
          <div>
            <span>画像已准备好</span>
            <p>下一步，只说清楚这一次你想学什么。</p>
          </div>
          <Link className="primary-action" href="/match">
            填写本次问题
          </Link>
        </footer>
      </main>
    </AppFrame>
  );
}
