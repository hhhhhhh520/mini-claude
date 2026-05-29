"""Skill command handler for /skills and /skill commands.

Commands:
    /skills - List all available skills
    /skill <name> [args] - Invoke a skill by name
"""

from rich.panel import Panel
from rich.table import Table

from .base import CommandHandler, CommandContext, CommandResult


class SkillCommandHandler(CommandHandler):
    """Handle skill-related commands."""

    commands = ["/skills", "/skill"]

    async def handle(self, ctx: CommandContext) -> CommandResult:
        """Handle /skills and /skill commands."""
        cmd = ctx.command

        if cmd == "/skills":
            return self._list_skills(ctx)

        if cmd == "/skill":
            return await self._invoke_skill(ctx)

        return CommandResult(handled=False)

    def _list_skills(self, ctx: CommandContext) -> CommandResult:
        """List all available skills."""
        from ...skills.registry import get_skill_registry

        registry = get_skill_registry()
        skills = registry.list_skills()

        if not skills:
            return CommandResult(
                handled=True,
                message="[dim]No skills loaded. Place SKILL.md files in ~/.mini-claude/skills/<name>/SKILL.md[/]",
            )

        table = Table(title="Available Skills")
        table.add_column("Name", style="bold cyan")
        table.add_column("Description")
        table.add_column("Source", style="dim")

        for skill in skills:
            desc_first_line = skill.description.split("\n")[0][:60] if skill.description else ""
            table.add_row(skill.name, desc_first_line, str(skill.source_path.parent.name))

        ctx.display.console.print(table)
        return CommandResult(handled=True)

    async def _invoke_skill(self, ctx: CommandContext) -> CommandResult:
        """Invoke a skill by name, injecting its body into the conversation."""
        from ...skills.registry import get_skill_registry

        args = ctx.args.strip()
        if not args:
            return CommandResult(
                handled=True,
                message="[dim]Usage: /skill <name> [arguments][/]",
            )

        # Parse skill name and optional arguments
        parts = args.split(None, 1)
        skill_name = parts[0]
        skill_args = parts[1] if len(parts) > 1 else ""

        registry = get_skill_registry()
        skill = registry.get(skill_name)

        if skill is None:
            available = [s.name for s in registry.list_skills()]
            return CommandResult(
                handled=True,
                error=f"Skill '{skill_name}' not found. Available: {', '.join(available) if available else 'none'}",
            )

        # Store the active skill in the session for the next graph invocation
        ctx.session._active_skill = skill
        ctx.session._active_skill_args = skill_args

        ctx.display.console.print(
            f"[green]Skill '{skill.name}' loaded.[/] "
            + (f"[dim]Args: {skill_args}[/]" if skill_args else "")
        )
        return CommandResult(handled=True)

    def get_help_text(self) -> str:
        """Get help text for skill commands."""
        return (
            "/skills - List all available skills\n"
            "/skill <name> [args] - Invoke a skill by name"
        )
