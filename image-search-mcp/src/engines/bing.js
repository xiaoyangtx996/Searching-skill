import { sleep, extractPageText } from "../utils.js";

export const name = "bing";

export async function search(context, imagePath) {
  const page = await context.newPage();
  try {
    await page.goto("https://www.bing.com/visualsearch", {
      waitUntil: "domcontentloaded",
      timeout: 60000,
    });
    await sleep(4000);

    let input = await page.waitForSelector('input[type="file"]', {
      state: "attached",
      timeout: 25000,
    }).catch(() => null);

    if (!input) {
      const cam = await page.$('#sb_sbi, [aria-label*="image" i]');
      if (cam) await cam.click().catch(() => {});
      await sleep(2000);
      input = await page.waitForSelector('input[type="file"]', { state: "attached", timeout: 15000 }).catch(() => null);
    }

    if (!input) {
      return { engine: name, pageTitle: await page.title(), url: page.url(), results: [], text: "", error: "未找到上传控件" };
    }

    await input.setInputFiles(imagePath);
    await sleep(9000);
    await page.waitForLoadState("networkidle", { timeout: 25000 }).catch(() => {});
    await page.evaluate(() => window.scrollBy(0, 800)).catch(() => {});
    await sleep(2500);

    // 从 li.b_algo 提取标题+链接（bing 跳转链也保留），并提取可见域名
    const results = await page.evaluate((limit) => {
      const out = [];
      const seen = new Set();
      for (const li of document.querySelectorAll("li.b_algo")) {
        const a = li.querySelector("h2 a");
        if (!a) continue;
        const href = a.href;
        const title = (a.innerText || a.textContent || "").trim();
        if (!href || !title) continue;
        if (seen.has(href)) continue;
        seen.add(href);
        // 页面上显示的来源域名
        const cite = li.querySelector("cite") || li.querySelector('[class*="cite"]');
        const source = cite ? (cite.innerText || "").trim() : "";
        out.push({ title: title.slice(0, 200), url: href, source: source.slice(0, 80) });
        if (out.length >= limit) break;
      }
      return out;
    }, 10);

    const text = await extractPageText(page, 3000);
    return { engine: name, pageTitle: await page.title(), url: page.url(), results, text };
  } finally {
    await page.close().catch(() => {});
  }
}
