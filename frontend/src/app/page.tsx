import Link from "next/link";

import { AppFrame } from "@/components/app-frame";
import { ReciprocityMark } from "@/components/reciprocity-mark";

export default function Home() {
  return (
    <AppFrame active="认证">
      <main className="landing-grid">
        <section className="landing-copy" aria-labelledby="landing-title">
          <p className="context-line">知乎内容提供证据，问题决定这次相遇</p>
          <h1 id="landing-title">
            你教我一块，
            <br />
            我补你一面。
          </h1>
          <p className="lead-copy">
            Verso
            不把相似的人继续困在一起。它从你授权的知乎内容里理解你能教什么，再寻找一个与你双向互补的人。
          </p>
          <div className="action-row">
            <Link className="primary-action" href="/profile">
              用知乎身份生成画像
            </Link>
            <Link className="text-action" href="/match">
              直接查看匹配演示
            </Link>
          </div>
          <p className="privacy-note">
            只读取本人授权的数据；知乎凭证仅保存在服务端，不进入浏览器。
          </p>
        </section>

        <section className="landing-visual" aria-label="双向互补关系示意">
          <ReciprocityMark />
          <div className="principle-strip">
            <span>不是推荐相似</span>
            <strong>而是找到缺口</strong>
          </div>
        </section>
      </main>
    </AppFrame>
  );
}
