/**
 * 这段逻辑跑在知乎页面的浏览器上下文里，不是 Verso React 树里。
 * 工作台只负责：打开命名窗口、生成书签、轮询队列。
 * 跳到知乎域之后，本站组件卸载，只能靠书签把脚本注入到知乎页。
 */

export const ZHIHU_WINDOW_NAME = "verso-zhihu";
export const ZHIHU_HOME_URL = "https://www.zhihu.com/";

export const ZHIHU_BODY_SELECTORS = [
  ".Post-RichText",
  ".RichText",
  ".RichContent-inner",
  ".Post-content",
].join(",");

export type ArchivableTarget = {
  collection: "articles" | "answers";
  contentId: string;
};

export function parseArchivableHref(href: string): ArchivableTarget | null {
  try {
    const url = new URL(href);
    const host = (url.hostname || "").toLowerCase();
    const path = url.pathname || "";
    if (host === "zhuanlan.zhihu.com" || host === "www.zhuanlan.zhihu.com") {
      const match = /^\/p\/(\d+)\/?$/.exec(path);
      return match ? { collection: "articles", contentId: match[1] } : null;
    }
    if (host === "www.zhihu.com" || host === "zhihu.com") {
      const match =
        /^\/question\/\d+\/answer\/(\d+)\/?$/.exec(path) ||
        /^\/answer\/(\d+)\/?$/.exec(path);
      return match ? { collection: "answers", contentId: match[1] } : null;
    }
    return null;
  } catch {
    return null;
  }
}

export function findEntityInState(
  value: unknown,
  collection: ArchivableTarget["collection"],
  contentId: string,
  seen: WeakSet<object> = new WeakSet(),
): Record<string, unknown> | null {
  if (value === null || typeof value !== "object") {
    return null;
  }
  if (seen.has(value)) {
    return null;
  }
  seen.add(value);
  const record = value as Record<string, unknown>;
  const bag = record[collection];
  if (bag && typeof bag === "object" && !Array.isArray(bag)) {
    const entity = (bag as Record<string, unknown>)[contentId];
    if (entity && typeof entity === "object" && !Array.isArray(entity)) {
      return entity as Record<string, unknown>;
    }
  }
  for (const nested of Object.values(record)) {
    const found = findEntityInState(nested, collection, contentId, seen);
    if (found) {
      return found;
    }
  }
  return null;
}

export function contentHtmlFromEntity(
  entity: Record<string, unknown> | null,
): string {
  if (!entity) {
    return "";
  }
  const content = entity.content;
  return typeof content === "string" ? content : "";
}

export function extractZhihuArticleHtml(root: ParentNode = document): string {
  const href = typeof location === "undefined" ? "" : location.href;
  const target = parseArchivableHref(href);
  if (target && root === document) {
    const state = readPageState();
    const html = contentHtmlFromEntity(
      state
        ? findEntityInState(state, target.collection, target.contentId)
        : null,
    );
    if (html) {
      return html;
    }
  }
  const node = root.querySelector(ZHIHU_BODY_SELECTORS);
  return node instanceof HTMLElement ? node.innerHTML : "";
}

function readPageState(): unknown {
  const win = window as Window & { __INITIAL_STATE__?: unknown };
  if (win.__INITIAL_STATE__) {
    return win.__INITIAL_STATE__;
  }
  const node = document.getElementById("js-initialData");
  if (!node?.textContent) {
    return null;
  }
  try {
    return JSON.parse(node.textContent);
  } catch {
    return null;
  }
}

export function captureApiBase(): string {
  if (process.env.NEXT_PUBLIC_API_BASE) {
    return process.env.NEXT_PUBLIC_API_BASE.replace(/\/$/, "");
  }
  if (typeof window !== "undefined") {
    return window.location.origin;
  }
  return "";
}

export function zhihuCaptureEndpoint(): string {
  return `${captureApiBase()}/me/articles/browser-capture`;
}

/** 注入到知乎页：优先读页面初始状态，再退回富文本 DOM。不读取知乎 Cookie。 */
export function captureBookmarklet(token: string): string {
  const endpoint = zhihuCaptureEndpoint();
  const selectors = ZHIHU_BODY_SELECTORS;
  const script = `void((async()=>{const href=location.href;const path=location.pathname||'';let col=null,id=null;const am=/^\\/p\\/(\\d+)\\/?$/.exec(path);const nm=/^\\/question\\/\\d+\\/answer\\/(\\d+)\\/?$/.exec(path)||/^\\/answer\\/(\\d+)\\/?$/.exec(path);if(location.hostname.indexOf('zhuanlan')>=0&&am){col='articles';id=am[1];}else if(nm){col='answers';id=nm[1];}function find(v,c,i,s){if(!v||typeof v!=='object')return null;if(s.has(v))return null;s.add(v);if(v[c]&&typeof v[c]==='object'&&v[c][i]&&typeof v[c][i]==='object')return v[c][i];for(const n of Object.values(v)){const f=find(n,c,i,s);if(f)return f;}return null;}let html='';try{const st=window.__INITIAL_STATE__||JSON.parse(document.getElementById('js-initialData')?.textContent||'null');if(col&&id&&st){const ent=find(st,col,id,new WeakSet());if(typeof ent?.content==='string')html=ent.content;}}catch(e){}if(!html)html=document.querySelector(${JSON.stringify(selectors)})?.innerHTML||'';if(!html){alert('这一页没有找到正文');return;}try{const r=await fetch(${JSON.stringify(endpoint)},{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({token:${JSON.stringify(token)},source_url:href,title:document.title,html})});const j=await r.json();alert(j.code===200?'已把正文发回 Verso':(j.message||'保存失败'));}catch(e){alert('保存失败');}})())`;
  return `javascript:${script}`;
}
