"""Web fetch tool for retrieving page content from URLs."""

import asyncio
import ipaddress
import socket
from typing import Dict, Any, Tuple
from urllib.parse import urlparse, urljoin

import httpx
from bs4 import BeautifulSoup

from .base import BaseTool, register_tool
from ._http import get_shared_client

MAX_REDIRECTS = 5


def _check_ssrf(url: str) -> Tuple[bool, str]:
    """Check a URL for SSRF vulnerabilities.

    Validates scheme, hostname, IP address, and DNS resolution to prevent
    server-side request forgery attacks.

    Args:
        url: The URL to validate

    Returns:
        Tuple of (is_safe, reason). is_safe=True means the URL is safe to fetch.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return False, f"Only HTTP/HTTPS URLs are allowed, got: {parsed.scheme}://"

    hostname = parsed.hostname or ""
    if hostname in ("localhost", "127.0.0.1", "::1", "0.0.0.0"):
        return False, "Access to localhost is not allowed"
    if hostname.startswith("169.254."):
        return False, "Access to link-local addresses is not allowed"

    # Strip IPv6 brackets
    if hostname.startswith("[") and hostname.endswith("]"):
        hostname = hostname[1:-1]

    # Check IP address (including IPv4-mapped IPv6 and decimal IP)
    try:
        ip = ipaddress.ip_address(hostname)
        if ip.is_private or ip.is_loopback or ip.is_link_local:
            return False, "Access to private/internal addresses is not allowed"
        if hasattr(ip, "ipv4_mapped") and ip.ipv4_mapped:
            mapped = ip.ipv4_mapped
            if mapped.is_private or mapped.is_loopback or mapped.is_link_local:
                return False, "Access to private/internal addresses is not allowed"
    except ValueError:
        try:
            ip = ipaddress.ip_address(int(hostname))
            if ip.is_private or ip.is_loopback or ip.is_link_local:
                return False, "Access to private/internal addresses is not allowed"
        except (ValueError, OverflowError):
            pass  # Not an IP, treat as domain name

    # DNS rebinding protection
    try:
        resolved_ips = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
        for family, _, _, _, sockaddr in resolved_ips:
            ip = ipaddress.ip_address(sockaddr[0])
            if ip.is_private or ip.is_loopback or ip.is_link_local:
                return False, "DNS resolution points to private/internal address"
    except (socket.gaierror, OSError):
        pass  # DNS failure will be caught by requests.get()

    return True, "OK"


class WebFetchTool(BaseTool):
    """Fetch and extract readable content from a URL."""

    @property
    def name(self) -> str:
        return "web_fetch"

    @property
    def description(self) -> str:
        return (
            "Fetch and extract the main text content from a URL. "
            "Use this AFTER web_search to get detailed information from the most relevant result page. "
            "Returns the page title and cleaned text content (max 3000 characters)."
        )

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "The URL to fetch content from",
                },
                "max_length": {
                    "type": "integer",
                    "description": "Maximum characters of content to return (default: 3000)",
                    "default": 3000,
                },
            },
            "required": ["url"],
        }

    async def execute(self, url: str, max_length: int = 3000) -> str:
        """Fetch and extract content from a URL.

        非阻塞实现（对标 Claude Code 的 WebFetch）：共享 httpx.AsyncClient +
        asyncio；SSRF 检查含 socket.getaddrinfo（阻塞调用），经 asyncio.to_thread
        卸载到线程池——多 Agent 并行时抓取互不拖累。
        注意不能用"每调用新建 AsyncClient"：其构造会同步加载 SSL 证书库
        （Windows ~0.2s），在事件循环上就是全局冻结，见 tools/_http.py。
        """
        try:
            # Initial SSRF check
            is_safe, reason = await asyncio.to_thread(_check_ssrf, url)
            if not is_safe:
                return f"Error: {reason}"

            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            }

            # Manual redirect loop with SSRF check on each hop
            current_url = url
            client = get_shared_client()
            for _ in range(MAX_REDIRECTS + 1):
                resp = await client.get(current_url, headers=headers, follow_redirects=False)

                if resp.status_code in (301, 302, 303, 307, 308):
                    next_url = resp.headers.get("Location", "")
                    if not next_url:
                        break
                    next_url = urljoin(current_url, next_url)
                    is_safe, reason = await asyncio.to_thread(_check_ssrf, next_url)
                    if not is_safe:
                        return f"Error: Redirect to blocked address: {reason}"
                    current_url = next_url
                    continue

                resp.raise_for_status()
                break
            else:
                return f"Error: Too many redirects (max {MAX_REDIRECTS}) when fetching {url}"

            # httpx 的 .text 自带编码探测（headers charset → body 嗅探），
            # 不再需要 requests 时代的 apparent_encoding 二段式
            soup = BeautifulSoup(resp.text, "html.parser")

            # Remove non-content elements
            for tag in soup(
                [
                    "script",
                    "style",
                    "nav",
                    "footer",
                    "header",
                    "aside",
                    "noscript",
                    "iframe",
                    "form",
                    "button",
                    "input",
                ]
            ):
                tag.decompose()

            title = (
                soup.title.string.strip()
                if soup.title and soup.title.string
                else urlparse(url).netloc
            )

            # Try to find main content area
            main = (
                soup.find("main")
                or soup.find("article")
                or soup.find(role="main")
                or soup.find(id=lambda x: x and ("content" in x.lower() or "article" in x.lower()))
                or soup.find(
                    class_=lambda x: (
                        x and ("content" in " ".join(x).lower() or "article" in " ".join(x).lower())
                    )
                )
            )

            body = main or soup.body or soup
            text = body.get_text(separator="\n", strip=True)

            # Clean up: remove excessive newlines and short lines
            lines = [line.strip() for line in text.split("\n") if len(line.strip()) > 20]
            text = "\n".join(lines)

            if len(text) > max_length:
                text = text[:max_length] + "..."

            domain = urlparse(url).netloc
            return f"Content from {domain}:\nTitle: {title}\n\n{text if text else 'No readable text content found.'}"

        except httpx.TimeoutException:
            return f"Error: Request to {url} timed out after 15 seconds."
        except httpx.ConnectError:
            return f"Error: Could not connect to {url}. The site may be blocked or unavailable."
        except httpx.HTTPStatusError as e:
            return f"Error: HTTP {e.response.status_code} when fetching {url}"
        except Exception as e:
            return f"Error fetching {url}: {type(e).__name__}: {str(e)}"


register_tool(WebFetchTool())
