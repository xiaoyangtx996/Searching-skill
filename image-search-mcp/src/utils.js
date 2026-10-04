export async function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

/** 通用结果解析：外部链接 + 标题 */
export async function extractGenericResults(page, limit = 12) {
  return page.evaluate((limit) => {
    const skipHost = /^(www\.)?(google|bing|yandex|baidu|microsoft|gstatic|googleusercontent)\.[a-z.]+$/i;
    const skipUrl = /(accounts\.|policies\.|support\.|about\.|preferences|\/sorry\/|showcaptcha|javascript:|^https?:\/\/[^/]+\/?(\?|#|$))/i;
    const out = [];
    const seen = new Set();
    for (const a of document.querySelectorAll("a[href]")) {
      const href = a.href;
      const text = (a.innerText || a.textContent || "").trim();
      if (!href || !href.startsWith("http")) continue;
      if (skipUrl.test(href)) continue;
      let host = "";
      try { host = new URL(href).hostname; } catch { continue; }
      if (skipHost.test(host)) continue;
      if (!text || text.length < 4) continue;
      const key = href.split("#")[0];
      if (seen.has(key)) continue;
      seen.add(key);
      out.push({ title: text.slice(0, 200), url: href });
      if (out.length >= limit) break;
    }
    return out;
  }, limit);
}

export async function extractPageText(page, maxLen = 4000) {
  return page.evaluate((maxLen) => {
    const t = document.body ? document.body.innerText : "";
    return t.replace(/\s+/g, " ").trim().slice(0, maxLen);
  }, maxLen);
}

export async function extractBaiduResults(page, limit = 10) {
  return page.evaluate((limit) => {
    const out = [];
    const seen = new Set();
    for (const a of document.querySelectorAll("a[href]")) {
      const href = a.href;
      const title = (a.innerText || a.textContent || "").trim();
      if (!href || !/^https?:/.test(href)) continue;
      if (/baidu\.com|bdstatic\.com|baidustatic/.test(href)) continue;
      if (!title || title.length < 3) continue;
      if (seen.has(href)) continue;
      seen.add(href);
      out.push({ title: title.slice(0, 200), url: href });
      if (out.length >= limit) break;
    }
    return out;
  }, limit);
}

/** 从结果页文本里提取"识别关键词"（Google/Bing 常把识别物放标题） */
export async function extractPageTitle(page) {
  return page.title();
}
