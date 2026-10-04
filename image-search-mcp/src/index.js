#!/usr/bin/env node
import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
} from "@modelcontextprotocol/sdk/types.js";

import { getContext, closeBrowser } from "./browser.js";
import { engines, engineNames } from "./engines/index.js";
import fs from "node:fs";
import path from "node:path";

const server = new Server(
  { name: "image-search-mcp", version: "1.0.0" },
  { capabilities: { tools: {} } }
);

server.setRequestHandler(ListToolsRequestSchema, async () => ({
  tools: [
    {
      name: "reverse_image_search",
      description:
        "以图搜图：把本地图片上传到指定识图引擎并返回结果（标题+链接）。" +
        "支持引擎：" + engineNames.join(", ") + "。",
      inputSchema: {
        type: "object",
        properties: {
          image_path: {
            type: "string",
            description: "本地图片的绝对路径",
          },
          engine: {
            type: "string",
            enum: engineNames,
            description: "识图引擎，默认 baidu",
          },
        },
        required: ["image_path"],
      },
    },
    {
      name: "reverse_image_search_all",
      description:
        "以图搜图（多引擎）：依次调用全部引擎并汇总结果，返回每个引擎的标题+链接列表。",
      inputSchema: {
        type: "object",
        properties: {
          image_path: { type: "string", description: "本地图片的绝对路径" },
          engines: {
            type: "array",
            items: { type: "string", enum: engineNames },
            description: "要使用的引擎列表，缺省为全部",
          },
        },
        required: ["image_path"],
      },
    },
  ],
}));

function assertImage(p) {
  const abs = path.resolve(p);
  if (!fs.existsSync(abs)) throw new Error("图片不存在: " + abs);
  const st = fs.statSync(abs);
  if (!st.isFile()) throw new Error("不是文件: " + abs);
  if (st.size > 30 * 1024 * 1024) throw new Error("图片超过 30MB");
  return abs;
}

server.setRequestHandler(CallToolRequestSchema, async (req) => {
  const { name, arguments: args } = req.params;

  try {
    if (name === "reverse_image_search") {
      const engineKey = args.engine || "baidu";
      const mod = engines[engineKey];
      if (!mod) throw new Error("未知引擎: " + engineKey);
      const abs = assertImage(args.image_path);

      const ctx = await getContext();
      const res = await mod.search(ctx, abs);

      const lines = [];
      lines.push("引擎: " + res.engine);
      if (res.pageTitle) lines.push("页面标题: " + res.pageTitle);
      lines.push("结果页: " + res.url);
      if (res.error) lines.push("⚠️ " + res.error);
      lines.push("");
      lines.push("结果 (" + res.results.length + " 条):");
      res.results.forEach((r, i) => {
        lines.push((i + 1) + ". " + r.title);
        lines.push("   " + r.url);
      });
      if (res.text) {
        lines.push("");
        lines.push("页面文本摘要:");
        lines.push(res.text.slice(0, 1500));
      }
      return { content: [{ type: "text", text: lines.join("\n") }] };
    }

    if (name === "reverse_image_search_all") {
      const abs = assertImage(args.image_path);
      const list = (args.engines && args.engines.length ? args.engines : engineNames).filter(
        (e) => engines[e]
      );
      const ctx = await getContext();
      const blocks = [];
      for (const e of list) {
        let res;
        try {
          res = await engines[e].search(ctx, abs);
        } catch (err) {
          blocks.push("### " + e + "\n错误: " + err.message);
          continue;
        }
        const b = ["### " + e, "结果页: " + res.url];
        if (res.error) b.push("⚠️ " + res.error);
        res.results.forEach((r, i) => b.push((i + 1) + ". " + r.title + "\n   " + r.url));
        blocks.push(b.join("\n"));
      }
      return { content: [{ type: "text", text: blocks.join("\n\n") }] };
    }

    throw new Error("未知工具: " + name);
  } catch (err) {
    return {
      content: [{ type: "text", text: "错误: " + (err && err.message ? err.message : String(err)) }],
      isError: true,
    };
  }
});

async function main() {
  const transport = new StdioServerTransport();
  await server.connect(transport);
}

process.on("exit", () => {
  closeBrowser();
});

main().catch((e) => {
  console.error("image-search-mcp 启动失败:", e);
  process.exit(1);
});
