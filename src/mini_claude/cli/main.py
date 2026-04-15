"""Main CLI entry point."""

import asyncio
import sys
from typing import Optional

import click
from dotenv import load_dotenv
from rich.panel import Panel

from .display import display
from .repl import REPLSession


def load_environment():
    """Load environment variables."""
    load_dotenv()


@click.group(invoke_without_command=True)
@click.option("--model", "-m", default=None, help="Model to use")
@click.option("--workspace", "-w", default=None, help="Workspace directory")
@click.option("--debug", is_flag=True, help="Enable debug mode")
@click.pass_context
def main(ctx, model: Optional[str], workspace: str, debug: bool):
    """Mini Claude Code - A multi-agent CLI assistant."""
    load_environment()
    ctx.ensure_object(dict)
    ctx.obj["model"] = model
    ctx.obj["workspace"] = workspace
    ctx.obj["debug"] = debug

    # If no subcommand, enter REPL mode
    if ctx.invoked_subcommand is None:
        ctx.invoke(repl)


@main.command()
@click.pass_context
def repl(ctx):
    """Start interactive REPL mode."""
    from mini_claude.config.settings import settings
    import os

    # Update workspace from context (use settings default if not specified)
    workspace = ctx.obj.get("workspace")
    if workspace:
        settings.workspace_root = os.path.abspath(workspace)

    # Show workspace info
    display.console.print(f"[dim]Workspace: {settings.workspace_root}[/]")

    # Start REPL session
    session = REPLSession()
    session.initialize()

    try:
        asyncio.run(session.run_graph())  # 使用 LangGraph 状态机
    except KeyboardInterrupt:
        display.console.print("\n[dim]Goodbye![/]")


@main.command()
@click.argument("prompt")
@click.option("--model", "-m", default=None, help="Model to use")
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
@click.pass_context
def ask(ctx, prompt: str, model: Optional[str], output_json: bool):
    """Execute a single prompt and exit."""
    import json
    from ..llm.provider import LLMProvider, convert_tools_to_litellm
    from ..tools import get_all_tools, execute_tool

    load_environment()

    async def run_single():
        llm = LLMProvider(model)
        display.user_message(prompt)
        display.show_thinking()

        # Get tools
        tools = get_all_tools()
        litellm_tools = convert_tools_to_litellm(tools)

        messages = [{"role": "user", "content": prompt}]

        try:
            # First call with tools
            response = await llm.chat(
                messages=messages,
                tools=litellm_tools,
                tool_choice="auto",
            )

            message = response.choices[0].message

            # Check for tool calls
            if hasattr(message, "tool_calls") and message.tool_calls:
                # Execute tools
                for tc in message.tool_calls:
                    tool_name = tc.function.name
                    tool_args = tc.function.arguments

                    if isinstance(tool_args, str):
                        tool_args = json.loads(tool_args)

                    print(f"[Tool] {tool_name}({tool_args})")
                    result = await execute_tool(tool_name, tool_args)

                    # Add assistant message and tool result
                    messages.append({"role": "assistant", "content": message.content or ""})
                    messages.append({"role": "user", "content": f"Tool {tool_name} result: {result}"})

                # Second call to process tool results
                response = await llm.chat(messages=messages)
                result_text = response.choices[0].message.content
            else:
                result_text = message.content or ""

            display.agent_message(result_text)
            return result_text
        except Exception as e:
            display.show_error(str(e))
            return None

    result = asyncio.run(run_single())


@main.command()
@click.pass_context
def status(ctx):
    """Show current status."""
    from mini_claude.config.settings import settings

    display.console.print(Panel.fit(
        f"[bold]Model:[/] {settings.default_model}\n"
        f"[bold]Workspace:[/] {settings.workspace_root}\n"
        f"[bold]Max Sub-Agents:[/] {settings.max_sub_agents}\n"
        f"[bold]Max Iterations:[/] {settings.max_iterations}",
        title="Status",
    ))


@main.command()
@click.argument("model")
@click.pass_context
def model(ctx, model: str):
    """Switch default model."""
    from mini_claude.config.settings import settings
    # This would need to update settings
    display.console.print(f"[dim]Model set to: {model}[/]")


if __name__ == "__main__":
    main()
