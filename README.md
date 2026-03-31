# TcmAiAgent

TCM(Traditional Chinese Medicine)是一个面向中医场景的“中医辨证分析” AI Agent 项目：支持用户输入图片与文字描述，生成辨证报告；并提供微信公众平台 webhook 接入入口。

## 目录结构

- `app/`：FastAPI 服务端
- `.cursor/skills/`：Cursor Skills 技术（中医辨证技能与输出规范）

## 快速开始

1. 安装依赖

```bash
python3 -m pip install -U pip
python3 -m pip install -r requirements.txt
```

2. 启动服务

```bash
./run.sh
```

如需指定端口/关闭自动端口探测：

```bash
PORT=8000 HOST=0.0.0.0 RELOAD=1 ./run.sh
```

3. 测试诊断接口（不走微信）

```bash
curl -X POST "http://localhost:8000/api/diagnose" \
  -F "text=我最近容易上火、口苦、睡不好" \
  -F "image=@/path/to/your.jpg"
```

返回字段：
- `report_md`：Markdown 报告（给网页/前端）
- `report_text`：微信更友好的纯文本版报告

## 环境变量（可选：接入 DeepSeek 进行图文分析）

如果未配置 `DEEPSEEK_API_KEY`，系统会降级为“基于文字的规则分析”（不做图片推断）。

说明：当前 LLM 调用已改为使用 LangChain（图片部分通过 `image_url` 发送）。

- `DEEPSEEK_API_URL`：默认 `https://api.deepseek.com/v1/chat/completions`
- `DEEPSEEK_API_KEY`：DeepSeek 鉴权 key（请在你环境中自行填入）
- `DEEPSEEK_MODEL`：默认 `deepseek-chat`
- `DEEPSEEK_VISION_MODEL`：（可选）图片/视觉模型名；不填则默认使用 `DEEPSEEK_MODEL`

说明：如果你只填了文本模型但图片模型不支持视觉，会自动降级为“仅基于文字分析”。

## 微信接入（必须配置）

微信“公众号/订阅号”的消息回调通常需要以下配置：

- `WECHAT_TOKEN`：用于 GET 签名校验
- `WECHAT_APPID`
- `WECHAT_APPSECRET`

接入后请求地址：`/wechat`

## 项目内的 Skills（Cursor）

项目代码会在生成报告时读取：

- `.cursor/skills/tcm-diagnosis/SKILL.md`

从而让输出结构与“中医辨证 + 建议”规范保持一致。

