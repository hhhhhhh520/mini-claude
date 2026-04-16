"""Web search tool using DuckDuckGo."""

import asyncio
from typing import Dict, Any, List
import socket
import urllib.error

from .base import BaseTool, register_tool


class WebSearchTool(BaseTool):
    """Search the web using DuckDuckGo."""

    @property
    def name(self) -> str:
        return "web_search"

    @property
    def description(self) -> str:
        return "Search the web for information. Returns a list of search results with titles, URLs, and snippets."

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query",
                },
                "num_results": {
                    "type": "integer",
                    "description": "Number of results to return (default: 5)",
                    "default": 5,
                },
            },
            "required": ["query"],
        }

    async def execute(self, query: str, num_results: int = 5) -> str:
        """Execute web search."""
        try:
            from duckduckgo_search import DDGS
        except ImportError:
            return "Error: duckduckgo-search not installed. Run: pip install duckduckgo-search -i https://pypi.tuna.tsinghua.edu.cn/simple"

        try:
            results = []
            with DDGS() as ddgs:
                for r in ddgs.text(query, max_results=num_results):
                    results.append({
                        "title": r.get("title", ""),
                        "url": r.get("href", ""),
                        "snippet": r.get("body", "")[:200],
                    })

            if not results:
                return f"No results found for: {query}"

            output = f"Search results for '{query}':\n\n"
            for i, r in enumerate(results, 1):
                output += f"{i}. {r['title']}\n"
                output += f"   URL: {r['url']}\n"
                output += f"   {r['snippet']}...\n\n"

            return output

        except socket.timeout:
            return f"Search error: Connection timed out. Please try again."
        except socket.gaierror as e:
            return f"Search error: DNS resolution failed. Please check your internet connection. ({e})"
        except ConnectionError:
            return f"Search error: Connection failed. Please check your internet connection."
        except urllib.error.URLError as e:
            return f"Search error: URL error - {e.reason}"
        except asyncio.TimeoutError:
            return f"Search error: Request timed out. Please try again."
        except Exception as e:
            # Provide more specific error messages based on error type
            error_msg = str(e).lower()
            if "timeout" in error_msg:
                return f"Search error: Request timed out. Please try again."
            elif "connection" in error_msg or "network" in error_msg:
                return f"Search error: Network connection issue. Please check your internet."
            elif "rate" in error_msg or "limit" in error_msg:
                return f"Search error: Rate limited. Please wait a moment and try again."
            else:
                return f"Search error: {str(e)}"


register_tool(WebSearchTool())
