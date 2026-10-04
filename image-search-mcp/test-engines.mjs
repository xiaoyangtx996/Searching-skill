import { getContext, closeBrowser } from "./src/browser.js";
import { engines } from "./src/engines/index.js";

const img = process.argv[2] || "C:/Users/MM/AppData/Roaming/Hermes/composer-images/image_0ab10e.png";
const want = (process.argv[3] || "baidu").split(",");
const ctx = await getContext();
for (const name of want) {
  const mod = engines[name];
  if (!mod) { console.log("未知引擎:", name); continue; }
  try {
    const r = await mod.search(ctx, img);
    console.log("引擎:", r.engine, "| 结果:", r.results?.length ?? 0, "| 页面标题:", r.pageTitle || "-", "| 错误:", r.error || "无");
    (r.results || []).slice(0, 8).forEach((x, i) => console.log(`  ${i + 1}. ${x.title}\n     ${x.url}`));
    if (r.text) console.log("  文本摘要:", r.text.slice(0, 600).replace(/\n/g, " "));
  } catch (e) {
    console.log("引擎", name, "异常:", String(e.message).slice(0, 300));
  }
}
await closeBrowser();
