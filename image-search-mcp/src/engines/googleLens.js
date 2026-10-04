import { sleep, extractGenericResults, extractPageText } from "../utils.js";

export const name = "googleLens";

export async function search(context, imagePath) {
  const page = await context.newPage();
  try {
    await page.goto("https://lens.google.com/", {
      waitUntil: "domcontentloaded",
      timeout: 60000,
    });
    await sleep(4000);

    let input =
      (await page.$('input[name="encoded_image"]')) ||
      (await page.$('input[type="file"]'));

    if (!input) {
      const btn = await page.$('button[aria-label*="图搜索"], [aria-label*="image search" i]');
      if (btn) await btn.click().catch(() => {});
      await sleep(2000);
      input = (await page.$('input[name="encoded_image"]')) || (await page.$('input[type="file"]'));
    }

    if (!input) {
      return { engine: name, pageTitle: await page.title(), url: page.url(), results: [], text: "", error: "未找到上传控件（可能需要登录/人机验证）" };
    }

    await input.setInputFiles(imagePath);
    await sleep(10000);
    await page.waitForLoadState("networkidle", { timeout: 25000 }).catch(() => {});

    const results = await extractGenericResults(page, 10);
    const text = await extractPageText(page, 3000);
    return { engine: name, pageTitle: await page.title(), url: page.url(), results, text };
  } finally {
    await page.close().catch(() => {});
  }
}
