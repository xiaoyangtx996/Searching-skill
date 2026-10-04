import { sleep, extractBaiduResults, extractPageText, extractGenericResults } from "../utils.js";

export const name = "baidu";

export async function search(context, imagePath) {
  const page = await context.newPage();
  try {
    await page.goto("https://graph.baidu.com/pcpage/index", {
      waitUntil: "domcontentloaded",
      timeout: 60000,
    });
    await sleep(3000);

    const input = await page.waitForSelector('input[type="file"]', {
      state: "attached",
      timeout: 25000,
    });
    await input.setInputFiles(imagePath);

    await sleep(8000);
    await page.waitForLoadState("networkidle", { timeout: 25000 }).catch(() => {});
    await sleep(2000);

    let results = await extractBaiduResults(page, 10);
    if (results.length === 0) results = await extractGenericResults(page, 10);
    const text = await extractPageText(page, 3000);
    return { engine: name, pageTitle: await page.title(), url: page.url(), results, text };
  } finally {
    await page.close().catch(() => {});
  }
}
