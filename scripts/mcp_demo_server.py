"""最小 MCP Server（streamable-http），用于验证「登记 → 发现 → Agent 调用」整条链路。

背景
----
平台支持把外部 MCP Server 的工具并入流水线工具注册表
（`MCP_INCLUDE_REGISTERED_SERVERS=true` 时生效，见 `app/mcp/config.py`），
但仓库里一直没有可跑的示例 Server，导致这条链路**从未被端到端验证过**：
所有实测都停在「对端不是 MCP Server，握手失败」。

本文件就是补这个缺口的对端。与 `scripts/search_gateway.py` 同类：
一个只依赖既有依赖（`mcp` 已在 `uv.lock`）、不引入新包的旁挂服务。

两个工具的返回值刻意设计成**不可伪造**：
- `deployment_probe_code` 回一个固定哨兵串。模型无法从权重里"猜到"它，
  报告里出现该串即证明它真的调到了本 Server；
- `text_fingerprint` 回 SHA-256 十六进制。可被独立计算复核，因此还能顺带
  验证"返回值在链路上没有被改写"。

部署（不修改 `deploy/compose.yaml`，用 `deploy/.env` 插值）：
    # deploy/.env
    EGRESS_INTERNAL_HOSTS=search-gateway,dapr-sidecar,redis,postgres,jaeger,mcp-demo

    docker run -d --name macp-mcp-demo \\
      --network multi-agent-collaboration-platform_internal \\
      --network-alias mcp-demo \\
      -v "$PWD/scripts/mcp_demo_server.py:/app/scripts/mcp_demo_server.py:ro" \\
      --entrypoint /app/.venv/bin/python \\
      multi-agent-collaboration-platform-backend:latest \\
      /app/scripts/mcp_demo_server.py

为什么端口是 8800：出网策略的 `EGRESS_ALLOWED_PORTS` 默认只放 443 与 8800，
且**端口检查在豁免逻辑之前**（`app/security/egress.py:190`），
所以自建内部 Server 只能落在这两个端口上，写别的端口加白名单也没用。
"""

from __future__ import annotations

import hashlib
import os

from mcp.server.fastmcp import FastMCP

PROBE_CODE = "MACP-MCP-OK-7F3C9A"

mcp = FastMCP(
    "macp-mcp-demo",
    host="0.0.0.0",
    port=int(os.getenv("MCP_DEMO_PORT", "8800")),
)


@mcp.tool()
def deployment_probe_code() -> str:
    """返回本次部署的 MCP 通道验证码。

    该串是本 Server 的唯一标识，任何其他工具都拿不到它。
    它出现在 Agent 的报告里，就说明这次调用真的经过了 MCP 通道。
    """

    return PROBE_CODE


@mcp.tool()
def text_fingerprint(text: str) -> str:
    """计算文本的 SHA-256 十六进制指纹。

    用于验证返回值在传输链路上未被改写：调用方可以独立算一遍比对。
    """

    return hashlib.sha256(text.encode("utf-8")).hexdigest()


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
