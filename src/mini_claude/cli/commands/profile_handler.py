"""Profile command handler for user profile management.

Commands:
    /profile - View user profile
    /profile model <name> - Set preferred model
    /profile language <lang> - Set preferred language
    /profile add-workflow <workflow> - Add common workflow
    /profile add-prompt <name> <prompt> - Add custom prompt
    /profile clear - Clear profile
"""

from rich.table import Table

from .base import CommandHandler, CommandContext, CommandResult


class ProfileCommandHandler(CommandHandler):
    """Handle /profile commands for user profile management."""

    commands = ["/profile"]

    async def handle(self, ctx: CommandContext) -> CommandResult:
        """Handle /profile command."""
        args = ctx.args.strip()

        # Ensure profile is loaded
        if not ctx.session._profile:
            ctx.session._load_profile()

        if not args:
            return self._view_profile(ctx)

        if args.startswith("model "):
            return self._set_model(ctx, args[6:].strip())

        if args.startswith("language "):
            return self._set_language(ctx, args[9:].strip())

        if args.startswith("add-workflow "):
            return self._add_workflow(ctx, args[13:].strip())

        if args.startswith("add-prompt "):
            return self._add_prompt(ctx, args[11:])

        if args == "clear":
            return self._clear_profile(ctx)

        return CommandResult(
            handled=True,
            message="[dim]Usage: /profile [model|language|add-workflow|add-prompt|clear] <value>[/]",
        )

    def _view_profile(self, ctx: CommandContext) -> CommandResult:
        """Display user profile."""
        profile = ctx.session._profile

        table = Table(title="User Profile")
        table.add_column("Field", style="cyan")
        table.add_column("Value", style="white")

        table.add_row("Preferred Model", profile.preferred_model)
        table.add_row("Preferred Language", profile.preferred_language)
        table.add_row("Recent Projects", str(len(profile.recent_projects)))
        table.add_row("Common Workflows", str(len(profile.common_workflows)))
        table.add_row("Custom Prompts", str(len(profile.custom_prompts)))
        table.add_row("Created At", profile.created_at or "N/A")
        table.add_row("Updated At", profile.updated_at or "N/A")

        ctx.display.console.print(table)

        # Show recent projects
        if profile.recent_projects:
            ctx.display.console.print("\n[bold]Recent Projects:[/]")
            for i, project in enumerate(profile.recent_projects[:5], 1):
                ctx.display.console.print(f"  {i}. {project}")

        # Show common workflows
        if profile.common_workflows:
            ctx.display.console.print("\n[bold]Common Workflows:[/]")
            for i, workflow in enumerate(profile.common_workflows[:5], 1):
                ctx.display.console.print(f"  {i}. {workflow}")

        # Show custom prompts
        if profile.custom_prompts:
            ctx.display.console.print("\n[bold]Custom Prompts:[/]")
            for name, prompt in profile.custom_prompts.items():
                ctx.display.console.print(f"  [cyan]{name}[/]: {prompt[:50]}...")

        return CommandResult(handled=True)

    def _set_model(self, ctx: CommandContext, model: str) -> CommandResult:
        """Set preferred model."""
        ctx.session._profile.preferred_model = model
        ctx.session._save_profile()
        return CommandResult(
            handled=True,
            message=f"[green]OK Preferred model set to: {model}[/]",
        )

    def _set_language(self, ctx: CommandContext, language: str) -> CommandResult:
        """Set preferred language."""
        ctx.session._profile.preferred_language = language
        ctx.session._save_profile()
        return CommandResult(
            handled=True,
            message=f"[green]OK Preferred language set to: {language}[/]",
        )

    def _add_workflow(self, ctx: CommandContext, workflow: str) -> CommandResult:
        """Add common workflow."""
        ctx.session._get_profile_manager().add_common_workflow(workflow)
        ctx.session._profile = ctx.session._get_profile_manager().load_profile()
        return CommandResult(
            handled=True,
            message=f"[green]OK Workflow added: {workflow}[/]",
        )

    def _add_prompt(self, ctx: CommandContext, args: str) -> CommandResult:
        """Add custom prompt."""
        parts = args.split(" ", 1)
        if len(parts) != 2:
            return CommandResult(
                handled=True,
                message="[red]Usage: /profile add-prompt <name> <prompt>[/]",
            )

        name, prompt = parts
        ctx.session._get_profile_manager().add_custom_prompt(name.strip(), prompt.strip())
        ctx.session._profile = ctx.session._get_profile_manager().load_profile()
        return CommandResult(
            handled=True,
            message=f"[green]OK Custom prompt '{name}' added[/]",
        )

    def _clear_profile(self, ctx: CommandContext) -> CommandResult:
        """Clear user profile."""
        ctx.session._get_profile_manager().clear_profile()
        ctx.session._profile = ctx.session._get_profile_manager().load_profile()
        return CommandResult(
            handled=True,
            message="[green]OK Profile cleared[/]",
        )

    def get_help_text(self) -> str:
        """Get help text for profile commands."""
        return (
            "/profile - View or edit user profile\n"
            "  /profile model <name> - Set preferred model\n"
            "  /profile language <lang> - Set preferred language\n"
            "  /profile add-workflow <workflow> - Add common workflow\n"
            "  /profile add-prompt <name> <prompt> - Add custom prompt\n"
            "  /profile clear - Clear profile"
        )
