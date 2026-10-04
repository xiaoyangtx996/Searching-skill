import * as baidu from "./baidu.js";
import * as bing from "./bing.js";
import * as googleLens from "./googleLens.js";

export const engines = {
  baidu,
  bing,
  googleLens,
};

export const engineNames = Object.keys(engines);
