<div align="center">

# KiroGate

**OpenAI & Anthropic 兼容的 Kiro IDE API 代理网关**

[![License: AGPL v3](https://img.shields.io/badge/License-AGPL%20v3-blue.svg)](https://www.gnu.org/licenses/agpl-3.0)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-green.svg)](https://fastapi.tiangolo.com/)

*通过任何支持 OpenAI 或 Anthropic API 的工具使用 Claude 模型*

[快速开始](#-快速开始) • [配置说明](#%EF%B8%8F-配置说明) • [API 参考](#-api-参考) • [使用示例](#-使用示例)

</div>

---

## 📦 快速开始

### Docker 一键启动（推荐）

```bash
docker run -d -p 8000:8000 \
  -e PROXY_API_KEY="your-password" \
  -e ADMIN_PASSWORD="your-admin-password" \
  -e ADMIN_SECRET_KEY="your-random-secret" \
  -v kirogate_data:/app/data \
  --name kirogate \
  ghcr.io/awei84/kirogate:main
```

### 本地安装

```bash
git clone https://github.com/awei84/KiroGate.git && cd KiroGate
pip install -r requirements.txt
cp .env.example .env  # 编辑 .env 填写凭证
python main.py
```

服务器启动在 `http://localhost:8000`

---

## ✨ 功能特性

| 功能 | 说明 |
|------|------|
| **双 API 兼容** | 同时支持 OpenAI 和 Anthropic API 格式 |
| **Claude Code 兼容** | `/cc/v1/messages` 缓冲端点，适配新版 Claude Code (2.1.9+) |
| **输出限制保护** | 🆕 自动注入提示词，解决 Write Failed / 会话卡死问题 |
| **WebSearch 工具** | 支持 Anthropic 官方的 web_search 工具 |
| **Extended Thinking** | 完整支持 Claude 扩展思考模式 |
| **多租户支持** | 组合模式 `PROXY_API_KEY:REFRESH_TOKEN` 支持多用户 |
| **用户系统** | LinuxDo/GitHub OAuth2 登录、Token 捐献、API Key 生成 |
| **Admin 后台** | 用户管理、Token 池管理、IP 黑名单等 |
| **智能重试** | 自动处理 403/429/5xx 错误 |
| **HTTP/SOCKS5 代理** | 支持代理访问 Kiro API |

---

## ⚙️ 配置说明

### 必填配置

```env
# 代理服务器密码（客户端认证用）
PROXY_API_KEY="your-password"

# 二选一：凭证文件 或 REFRESH_TOKEN
KIRO_CREDS_FILE="~/.aws/sso/cache/kiro-auth-token.json"
# 或
REFRESH_TOKEN="your-refresh-token"
```

### 可选配置

<details>
<summary>超时配置</summary>

```env
FIRST_TOKEN_TIMEOUT="120"      # 首个 token 超时（秒）
STREAM_READ_TIMEOUT="300"      # 流式读取超时（秒）
NON_STREAM_TIMEOUT="600"       # 非流式请求超时（秒）
```

</details>

<details>
<summary>输出限制（解决 Write Failed）</summary>

KiroGate 默认自动注入输出限制警告，避免模型输出过长被截断：

```env
INJECT_OUTPUT_LIMIT_WARNING=true   # 是否启用（默认 true）
OUTPUT_TOKEN_LIMIT=8192            # 输出限制（默认 8192）
```

如仍有问题，可在 Claude Code 客户端设置：

```bash
export CLAUDE_CODE_MAX_OUTPUT_TOKENS=14000
```

</details>

<details>
<summary>代理配置</summary>

```env
PROXY_URL="http://127.0.0.1:7890"   # 或 socks5://...
PROXY_USERNAME="user"               # 可选
PROXY_PASSWORD="pass"               # 可选
```

</details>

<details>
<summary>Admin 后台</summary>

```env
ADMIN_PASSWORD="your-admin-password"
ADMIN_SECRET_KEY="your-random-secret"
```

访问 `/admin` 进入管理后台

</details>

### 获取 Refresh Token

推荐使用 [Kiro Account Manager](https://github.com/chaogei/Kiro-account-manager) 轻松获取。

---

## 📡 API 参考

### 端点列表

| 端点 | 方法 | 说明 |
|------|------|------|
| `/v1/chat/completions` | POST | OpenAI 兼容 |
| `/v1/messages` | POST | Anthropic 兼容 |
| `/cc/v1/messages` | POST | Claude Code 兼容（缓冲模式） |
| `/v1/models` | GET | 可用模型列表 |

### 认证方式

**简单模式**（服务器配置 REFRESH_TOKEN）：
```
Authorization: Bearer {PROXY_API_KEY}
x-api-key: {PROXY_API_KEY}
```

**组合模式**（用户自带 Token）✨ 推荐：
```
Authorization: Bearer {PROXY_API_KEY}:{REFRESH_TOKEN}
x-api-key: {PROXY_API_KEY}:{REFRESH_TOKEN}
```

### 可用模型

`claude-opus-4-5` • `claude-sonnet-4-5` • `claude-sonnet-4` • `claude-haiku-4-5`

---

## 💡 使用示例

### Claude Code CLI

```bash
export ANTHROPIC_BASE_URL="http://localhost:8000"
export ANTHROPIC_API_KEY="your-proxy-key:your-refresh-token"
```

### Python OpenAI SDK

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:8000/v1",
    api_key="your-proxy-key:your-refresh-token"
)

response = client.chat.completions.create(
    model="claude-sonnet-4-5",
    messages=[{"role": "user", "content": "你好！"}]
)
```

### Python Anthropic SDK

```python
from anthropic import Anthropic

client = Anthropic(
    base_url="http://localhost:8000",
    api_key="your-proxy-key:your-refresh-token"
)

message = client.messages.create(
    model="claude-sonnet-4-5",
    max_tokens=1024,
    messages=[{"role": "user", "content": "你好！"}]
)
```

### cURL

```bash
# OpenAI 格式
curl http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer your-proxy-key" \
  -H "Content-Type: application/json" \
  -d '{"model": "claude-sonnet-4-5", "messages": [{"role": "user", "content": "你好"}]}'

# Anthropic 格式
curl http://localhost:8000/v1/messages \
  -H "x-api-key: your-proxy-key" \
  -H "Content-Type: application/json" \
  -d '{"model": "claude-sonnet-4-5", "max_tokens": 1024, "messages": [{"role": "user", "content": "你好"}]}'
```

---

## 🛠️ 高级功能

<details>
<summary>用户系统</summary>

支持 LinuxDo/GitHub OAuth2 登录：

```env
OAUTH_CLIENT_ID="your-client-id"
OAUTH_CLIENT_SECRET="your-client-secret"
```

用户可以：
- 捐献 Token 到公共池
- 生成 `sk-xxx` 格式的 API Key
- 查看使用统计

</details>

<details>
<summary>部署到 Fly.io</summary>

```bash
fly apps create kirogate
fly volumes create kirogate_data --region nrt --size 1
fly secrets set PROXY_API_KEY="your-password"
fly secrets set ADMIN_PASSWORD="your-admin-password"
fly secrets set ADMIN_SECRET_KEY="your-random-secret"
fly deploy
```

</details>

<details>
<summary>调试模式</summary>

```env
DEBUG_MODE=errors  # off / errors / all
```

日志保存在 `debug_logs/` 文件夹

</details>

---

## 📜 许可证

[AGPL-3.0](LICENSE) - 网络使用视为分发，修改后的版本必须公开源代码。

---

## 🙏 致谢

基于 [kiro-openai-gateway](https://github.com/Jwadow/kiro-openai-gateway) 开发，感谢 [@Jwadow](https://github.com/jwadow)。

---

## ⚠️ 免责声明

本项目与 AWS、Anthropic、Kiro IDE 无关。使用时请自行承担风险，遵守相关服务条款。
