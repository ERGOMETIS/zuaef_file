# 爬取层经验与优化记录（实战教训）

> 来源：PRA v0.2.0 与继任者 zuaef_file 的真实运行案例（JetPower、BEE GREEN、Lectric 等）。
> 本文档只记录**实测验证过**的经验，不记录理论推断。更新时间：2026-10-12。

## 1. 数据可信度红线（最高优先级）

- 每条信号必须带 `source_url` + 权威 `pubDate`。缺任一项的结论一律标记为 unconfirmed，不允许 LLM 判断时效。
- **RSS 优于 HTML 抓取**：RSS 结构稳定、带权威发布日期；HTML 抓取的日期经常是页面构建时间或缺失。能走 RSS 的源绝不走 HTML 选择器。
- 价格冲突不要"选一个"：如实保留为 unconfirmed 并记录两个来源（实测：catalog.md 里 SKU 全谱系 + 价格冲突如实保留，客户报告质量反而更高）。
- 图片字节哈希只证明"存了什么"，不证明"这是哪个型号"。型号归属是研究断言，需来源页 SKU/年款/市场三匹配 + 人审才能对客发布。

## 2. 搜索降级链与网络现状（2026-10 实测）

- 设计：Tavily → Brave → DuckDuckGo 三级降级，**查询失败绝不 raise**，返回诚实空结果。
- 本机现状：无 TAVILY/BRAVE key，DDG 被墙（TUN 代理握手后无数据，curl 10s 超时）。bing.com 可达 ~0.8s。
- 兜底：web_search 空结果时，agent 靠 `web_fetch` 直抓目标域名兜底。配 `TAVILY_API_KEY` 即恢复搜索主链。
- 教训：不要假设任何单一搜索入口可用；空结果要"诚实空"，不要编造。

## 3. 模型失败模式与强制兜底

DeepSeek V4.1 Flash 实测两种失败模式，都会导致"跑完了但没报告"：

1. **只抓页面不写文件**：agent 拿到抓取结果后不落盘，会话结束产物丢失。
2. 会话提前收敛：认为"信息够了"提前收尾，report.md 未生成。

- 对策：**CLI 交付物强制循环**——以 report.md/catalog.md 是否真实落盘为完成判据，缺产物就继续循环，不信任模型自述"已完成"。
- 无审批门：用户红线，不加任何 HITL/审批步骤。边界靠预算停止（`--request-limit`）、数据红线、质量规则实现。

## 4. 移植层架构经验（已验证的模块设计）

- `web_security.py`：SSRF **前后双查**（请求前解析 DNS 校验 + 响应后校验重定向目标），云 metadata 地址（169.254.169.254 等）硬封锁。
- `acquisition.py`：crawl4ai → httpx **双适配器**，环境缺 heavy 依赖时自动降级 httpx，不挂。
- Shopify 快路径：`/products.json` / 商品页内嵌 JSON 直读，绕过 HTML 解析，快且稳。spec 区域标记截断，避免把页面全文塞进上下文。
- `search.py`：查询失败绝不 raise（见 §2）。
- 原生 WebFetch/WebSearch 可用时优先用原生，本地模块是 **fallback**，不是替代。

## 5. 源扩展原则

- 按**维度**扩展（德国/法国/cargo/OEM/荷兰/日本/保险……），不加同维度数量。同维度堆源没有边际价值。
- 每接一个新源先验证：RSS 可用性、pubDate 权威性、内容是否垂直（e-bike 相关）。不垂直的源不接。

## 6. 工程协作教训

- 四模块移植（~1400 行 + 测试）在慢模型上 delegate_task 600s 必超时（两次验证）。重活主会话直接干，不委派。
- 子代理会"写完文件才超时"：超时后先 `git status` 捞残局自己收尾，别盲目重派。
- `hermes config set delegation.provider/model` 对运行中 gateway 会话已派出的子代理不生效，需新会话。
- 终端子进程默认无 API 凭据，跑脚本前先加载 Hermes 环境文件，否则 401。
