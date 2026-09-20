/**
 * 这段逻辑跑在知乎页面的浏览器上下文里，不是 Verso React 树里。
 * Verso 设置页只负责：确认你已登录、打开失败文章、生成这段脚本。
 * 跳到 zhuanlan.zhihu.com 之后，本站组件卸载，只能靠书签把脚本注入到知乎页。
 */

export const ZHIHU_BODY_SELECTORS = [
  ".Post-RichText",
  ".RichText",
  ".RichContent-inner",
  ".Post-content",
].join(",");

export function extractZhihuArticleHtml(root: ParentNode = document): string {
  const node = root.querySelector(ZHIHU_BODY_SELECTORS);
  return node instanceof HTMLElement ? node.innerHTML : "";
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

/** 注入到知乎页：取正文 HTML，POST 回 Verso。不读取、不上传知乎 Cookie。 */
export function captureBookmarklet(token: string): string {
  const endpoint = zhihuCaptureEndpoint();
  const selectors = ZHIHU_BODY_SELECTORS;
  const script = `void((async()=>{const html=document.querySelector(${JSON.stringify(selectors)})?.innerHTML||'';if(!html){alert('这一页没有找到正文');return;}try{const r=await fetch(${JSON.stringify(endpoint)},{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({token:${JSON.stringify(token)},source_url:location.href,title:document.title,html})});const j=await r.json();alert(j.code===200?'已把正文发回 Verso':(j.message||'保存失败'));}catch(e){alert('保存失败');}})())`;
  return `javascript:${script}`;
}
