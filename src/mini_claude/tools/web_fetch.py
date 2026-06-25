"""Web fetch tool for retrieving page content from URLs."""

from typing import Dict, Any
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from .base import BaseTool, register_tool


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
        """Fetch and extract content from a URL."""
        try:
            # URL 安全校验 - 防止 SSRF
            parsed = urlparse(url)
            if parsed.scheme not in ("http", "https"):
                return f"Error: Only HTTP/HTTPS URLs are allowed, got: {parsed.scheme}://"
            hostname = parsed.hostname or ""
            if hostname in ("localhost", "127.0.0.1", "::1", "0.0.0.0"):
                return "Error: Access to localhost is not allowed"
            if hostname.startswith("169.254."):
                return "Error: Access to link-local addresses is not allowed"
            # 检查私有 IP 范围
            import ipaddress
            try:
                ip = ipaddress.ip_address(hostname)
                if ip.is_private or ip.is_loopback or ip.is_link_local:
                    return "Error: Access to private/internal addresses is not allowed"
            except ValueError:
                pass  # 不是 IP 地址，是域名，允许

            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            }

            resp = requests.get(url, headers=headers, timeout=15, allow_redirects=True)
            resp.raise_for_status()
            resp.encoding = resp.apparent_encoding

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

        except requests.exceptions.Timeout:
            return f"Error: Request to {url} timed out after 15 seconds."
        except requests.exceptions.ConnectionError:
            return f"Error: Could not connect to {url}. The site may be blocked or unavailable."
        except requests.exceptions.HTTPError as e:
            return f"Error: HTTP {e.response.status_code} when fetching {url}"
        except requests.exceptions.TooManyRedirects:
            return f"Error: Too many redirects when fetching {url}"
        except Exception as e:
            return f"Error fetching {url}: {type(e).__name__}: {str(e)}"


register_tool(WebFetchTool())
