import { chromium } from "playwright";

let browser = null;
let context = null;

const UA =
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 " +
  "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36";

export async function getContext() {
  if (context) return context;

  browser = await chromium.launch({
    headless: process.env.HEADLESS !== "false",
    args: [
      "--disable-blink-features=AutomationControlled",
      "--no-sandbox",
    ],
  });

  context = await browser.newContext({
    userAgent: UA,
    viewport: { width: 1440, height: 900 },
    locale: "zh-CN",
    timezoneId: "Asia/Shanghai",
    extraHTTPHeaders: {
      "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    },
  });

  // 抹掉 navigator.webdriver 痕迹，降低被识别概率
  await context.addInitScript(() => {
    Object.defineProperty(navigator, "webdriver", { get: () => undefined });
  });

  return context;
}

export async function closeBrowser() {
  try {
    if (browser) await browser.close();
  } catch {}
  browser = null;
  context = null;
}

process.on("SIGINT", async () => {
  await closeBrowser();
  process.exit(0);
});
