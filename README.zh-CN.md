# Open Product Research Agent：开源产品竞品调研 Agent

一个**独立于 ZUAEF 的原生 PydanticAI Harness 项目**，可以从品牌官网、型号或客户需求开始，收集来源、整理车型、下载真实商品照片，并生成客户可读 PDF。它不是另一个 Agent Runtime。

## 最短启动方法

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
product-research init cases/first-client \
  --lead 'https://品牌官网地址/' \
  --market '荷兰' \
  --goal '电助力自行车全系竞品调研与工厂开发机会'

# 配置当前所选模型提供商的 API Key；下面仅为示例
export OPENAI_API_KEY='...'
product-research run cases/first-client --model openai:YOUR_MODEL
product-research render cases/first-client --preview
```

详见 [英文 README](README.md) 的官方 API 装配示例、安全及图片授权说明。

## 实现边界

- **PydanticAI 原生执行**：Model、Agent Loop、WebSearch、WebFetch、LocalWorkspace、Harness FileSystem。
- **本项目自己负责**：竞品商业研究语义、真实图片采集与来源记录、Markdown 转 PDF、逐页预览。
- **不做**：自研 Harness、Web UI、状态机、通用 Schema、虚拟证据门禁、Agent 路由器、自动编造销售额或出厂价。
- **真实性要求**：图片抓取成功只证明文件有效，不证明 SKU 对应准确，也不等于取得版权授权。必须核对具体款式、年份和市场。
- **现在的验证状态**：离线测试验证了工具与渲染；真实模型从官网到客户交付报告的端到端运行，仍需要配置模型/API，在一个未见过的品牌上正式验证。

## 建议的首个开源版本

MIT 授权、单一 Agent 和 Capability、可安装 CLI、真实来源与图片、PDF 输出。不发布之前的客户报告、私有仓库代码、内部配置或品牌图片。
