"""Web search tool using DuckDuckGo via ddgs library."""

from typing import Dict, Any

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

    @property
    def examples(self) -> list:
        return [
            {
                "description": "Search for Python documentation",
                "input": {"query": "Python asyncio tutorial", "num_results": 5},
                "expected_output": "Search results for 'Python asyncio tutorial'\n\n1. Asyncio Tutorial\n   URL: https://...",
            },
            {
                "description": "Search for error solution",
                "input": {"query": "ModuleNotFoundError numpy solution"},
                "expected_output": "Search results for 'ModuleNotFoundError numpy solution'\n\n1. Stack Overflow Answer...",
            },
            {
                "description": "Search for latest news",
                "input": {"query": "latest AI developments 2024"},
                "expected_output": "Search results for 'latest AI developments 2024'...",
            },
        ]

    async def execute(self, query: str, num_results: int = 5) -> str:
        """Execute web search with fallback for complex queries."""
        try:
            from ddgs import DDGS
        except ImportError:
            return "Error: ddgs not installed. Run: pip install ddgs -i https://pypi.tuna.tsinghua.edu.cn/simple"

        queries = [query]

        # If query contains date numbers, add a simplified version as fallback
        import re

        simplified = re.sub(r"\d{4}年\d{1,2}月\d{1,2}日?", "", query).strip()
        simplified = re.sub(r"\d{4}[-/]\d{1,2}[-/]\d{1,2}", "", simplified).strip()
        if simplified and simplified != query:
            queries.append(simplified)

        last_error = None
        for q in queries:
            try:
                results = []
                with DDGS(timeout=15) as ddgs:
                    for r in ddgs.text(q, max_results=num_results):
                        results.append(
                            {
                                "title": r.get("title", ""),
                                "url": r.get("href", ""),
                                "snippet": r.get("body", "")[:200],
                            }
                        )

                if results:
                    prefix = (
                        f"Search results for '{q}'"
                        if q == query
                        else f"Search results (simplified from '{query}'):"
                    )
                    output = f"{prefix}\n\n"
                    for i, r in enumerate(results, 1):
                        output += f"{i}. {r['title']}\n"
                        output += f"   URL: {r['url']}\n"
                        output += f"   {r['snippet']}...\n\n"
                    return output

                last_error = f"No results found for: {q}"

            except Exception as e:
                last_error = str(e)
                continue  # try simplified query

        # All queries failed
        error_msg = str(last_error).lower() if last_error else ""
        if "timeout" in error_msg:
            return "Search error: Connection timed out. Please try again."
        elif "connection" in error_msg or "network" in error_msg:
            return "Search error: Network connection issue. Please check your internet."
        elif "rate" in error_msg or "limit" in error_msg:
            return "Search error: Rate limited. Please wait a moment and try again."
        elif "no results" in error_msg:
            return str(last_error)
        else:
            return f"Search error: {last_error}. Try a simpler query without specific dates."


register_tool(WebSearchTool())
