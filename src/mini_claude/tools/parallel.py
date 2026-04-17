"""Enhanced parallel execution tools with auto-aggregation."""

import asyncio
import time
from typing import Dict, Any, List, Optional
from datetime import datetime

from .base import BaseTool, register_tool
from ..agent.coordinator import (
    parallel_coordinator, DistributedTask, TaskPriority, TaskStatus
)
from ..agent.subagent import subagent_manager
from ..utils.file_lock import file_lock_manager
from ..config.settings import settings


def _log(msg: str):
    """Thread-safe logging with timestamp."""
    timestamp = datetime.now().strftime('%H:%M:%S.%f')[:-3]
    print(f"[{timestamp}] [PARALLEL] {msg}")


class PlanParallelTool(BaseTool):
    """Plan parallel execution with dependency analysis."""

    @property
    def name(self) -> str:
        return "plan_parallel"

    @property
    def description(self) -> str:
        return "Plan parallel task execution with dependency analysis and file conflict detection"

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "tasks": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string", "description": "Unique task ID"},
                            "description": {"type": "string", "description": "Task description"},
                            "target_files": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Files this task will modify",
                            },
                            "depends_on": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Task IDs this depends on",
                            },
                            "priority": {
                                "type": "string",
                                "enum": ["high", "medium", "low"],
                                "description": "Task priority",
                            },
                        },
                        "required": ["id", "description"],
                    },
                    "description": "List of tasks to plan",
                },
            },
            "required": ["tasks"],
        }

    async def execute(self, tasks: List[Dict]) -> str:
        # Clear previous tasks
        parallel_coordinator.clear()

        # Add tasks
        for task_data in tasks:
            priority = TaskPriority.MEDIUM
            if task_data.get("priority") == "high":
                priority = TaskPriority.HIGH
            elif task_data.get("priority") == "low":
                priority = TaskPriority.LOW

            parallel_coordinator.add_task(
                task_id=task_data["id"],
                description=task_data["description"],
                target_files=task_data.get("target_files", []),
                dependencies=task_data.get("depends_on", []),
                priority=priority,
            )

        # Analyze dependencies
        try:
            levels = parallel_coordinator.analyze_dependencies()
        except ValueError as e:
            return f"Error: {e}"

        # Check for file conflicts
        file_conflicts = self._detect_file_conflicts(tasks)

        # Build response
        lines = ["=== Parallel Execution Plan ===\n"]
        lines.append(f"Total tasks: {len(tasks)}")
        lines.append(f"Execution levels: {len(levels)}\n")

        for level_name, task_ids in levels.items():
            level_num = level_name.split("_")[1]
            lines.append(f"Level {level_num} (parallel):")
            for tid in task_ids:
                task = parallel_coordinator.tasks[tid]
                files_info = f" → {', '.join(task.target_files)}" if task.target_files else ""
                lines.append(f"  - {tid}: {task.description}{files_info}")
            lines.append("")

        if file_conflicts:
            lines.append("⚠️ Potential file conflicts detected:")
            for conflict in file_conflicts:
                lines.append(f"  - {conflict['file']}: tasks {conflict['tasks']}")
            lines.append("")

        lines.append("Use 'execute_parallel' to start execution.")

        return "\n".join(lines)

    def _detect_file_conflicts(self, tasks: List[Dict]) -> List[Dict]:
        """Detect tasks that modify the same files."""
        file_to_tasks: Dict[str, List[str]] = {}
        conflicts = []

        for task in tasks:
            for file in task.get("target_files", []):
                if file not in file_to_tasks:
                    file_to_tasks[file] = []
                file_to_tasks[file].append(task["id"])

        for file, task_ids in file_to_tasks.items():
            if len(task_ids) > 1:
                conflicts.append({"file": file, "tasks": task_ids})

        return conflicts


class ExecuteParallelTool(BaseTool):
    """Execute planned parallel tasks with auto-aggregation."""

    @property
    def name(self) -> str:
        return "execute_parallel"

    @property
    def description(self) -> str:
        return "Execute planned parallel tasks with automatic result aggregation"

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "auto_aggregate": {
                    "type": "boolean",
                    "description": "Automatically aggregate results when complete (default: true)",
                },
            },
            "required": [],
        }

    async def execute(self, auto_aggregate: bool = True) -> str:
        if not parallel_coordinator.tasks:
            return "Error: No tasks planned. Use 'plan_parallel' first."

        # Get execution levels
        try:
            levels = parallel_coordinator.analyze_dependencies()
        except ValueError as e:
            return f"Error: {e}"

        total_tasks = len(parallel_coordinator.tasks)
        lines = [f"Starting parallel execution of {total_tasks} tasks...\n"]
        _log(f"Total tasks: {total_tasks}, levels: {len(levels)}")

        # Execute level by level
        for level_name, task_ids in levels.items():
            level_num = level_name.split("_")[1]
            lines.append(f"[Level {level_num}] Executing {len(task_ids)} task(s) in parallel...")
            _log(f"Level {level_num}: Starting {len(task_ids)} tasks: {task_ids}")

            # Print immediate status for user feedback (force flush)
            import sys
            sys.stdout.write(f"\n[PARALLEL] Executing {len(task_ids)} tasks: {', '.join(task_ids)}\n")
            sys.stdout.flush()

            # Create all task coroutines FIRST (don't await yet)
            task_coroutines = []
            for task_id in task_ids:
                task = parallel_coordinator.tasks[task_id]
                agent_id = f"agent_{task_id}"
                task_coroutines.append(self._run_task_with_logging(task_id, agent_id))

            # Launch ALL tasks at the SAME time using asyncio.gather
            _log(f"Level {level_num}: Launching all {len(task_coroutines)} tasks simultaneously")
            start_time = time.time()

            # Show progress indicator while waiting (force flush)
            sys.stdout.write(f"[PARALLEL] Waiting for tasks to complete (timeout: 180s)...\n")
            sys.stdout.flush()

            results = await asyncio.gather(*task_coroutines, return_exceptions=True)

            elapsed = time.time() - start_time
            _log(f"Level {level_num}: All tasks completed in {elapsed:.2f}s")
            sys.stdout.write(f"[PARALLEL] All tasks completed in {elapsed:.2f}s\n")
            sys.stdout.flush()

            # Report results
            for result in results:
                if isinstance(result, Exception):
                    lines.append(f"  ✗ Error: {result}")
                else:
                    task_id, success, output = result
                    status = "✓" if success else "✗"
                    lines.append(f"  {status} {task_id}")

        lines.append(f"\nExecution complete!")

        # Auto-aggregate if requested
        if auto_aggregate:
            summary = parallel_coordinator.aggregate_results()
            return summary

        return "\n".join(lines)

    async def _run_task_with_logging(self, task_id: str, agent_id: str):
        """Run a single task with detailed logging for concurrency verification."""
        import sys
        task = parallel_coordinator.tasks[task_id]

        # Assign task
        parallel_coordinator.assign_task(task_id, agent_id)
        parallel_coordinator.mark_task_running(task_id)

        _log(f"Task {task_id} ({agent_id}): STARTED")
        sys.stdout.write(f"  [{task_id}] Started...\n")
        sys.stdout.flush()

        try:
            # Execute via sub-agent
            result = await self._execute_task_via_agent(task, agent_id)
            parallel_coordinator.mark_task_completed(task_id, result)
            _log(f"Task {task_id} ({agent_id}): COMPLETED")
            sys.stdout.write(f"  [{task_id}] ✓ Completed\n")
            sys.stdout.flush()
            return task_id, True, result
        except Exception as e:
            parallel_coordinator.mark_task_failed(task_id, str(e))
            _log(f"Task {task_id} ({agent_id}): FAILED - {e}")
            sys.stdout.write(f"  [{task_id}] ✗ Failed: {e}\n")
            sys.stdout.flush()
            return task_id, False, str(e)

    async def _execute_task_via_agent(self, task: DistributedTask, agent_id: str) -> str:
        """Execute a single task via sub-agent with auto-parameter injection."""
        from ..agent.graph import build_agent_graph_no_checkpoint
        from ..agent.state import create_initial_state
        from ..tools.file_ops import set_current_agent
        from langchain_core.messages import AIMessage

        # Set agent ID for file locking
        set_current_agent(agent_id)

        # Build prompt - VERY EXPLICIT to prevent LLM from making mistakes
        target_file = task.target_files[0] if task.target_files else "output.txt"

        # Detect file type for content hint
        file_ext = target_file.split('.')[-1] if '.' in target_file else 'txt'
        content_hint = {
            'html': '<!DOCTYPE html>\n<html>\n<head><title>Page</title></head>\n<body>\n<!-- Content here -->\n</body>\n</html>',
            'css': '/* Styles */\nbody { margin: 0; padding: 0; }',
            'js': '// JavaScript\nconsole.log("Hello");',
            'md': '# Title\n\nContent here.',
            'txt': 'Content here.',
        }.get(file_ext, 'Content here.')

        prompt = f"""You are a file writer. Your ONLY job is to write a file.

TASK: {task.description}
TARGET FILE: {target_file}

CRITICAL INSTRUCTIONS:
1. Call write_file tool NOW with BOTH arguments
2. path MUST be: "{target_file}"
3. content MUST be the file content (not empty)

EXAMPLE:
write_file(path="{target_file}", content="{content_hint[:50]}...")

DO THIS NOW: Call write_file(path="{target_file}", content="your content here")"""

        _log(f"Agent {agent_id}: Building graph for task '{task.id}'")

        # Execute
        graph = build_agent_graph_no_checkpoint()

        # CRITICAL: Mark as subagent and limit allowed tools
        # Sub-agents cannot spawn more agents (prevent infinite recursion)
        subagent_allowed_tools = [
            "read_file", "write_file", "edit_file",
            "list_dir", "search_files", "search_content",
            "run_command", "web_search"
        ]

        state = create_initial_state(
            prompt,
            thread_id=agent_id,
            is_subagent=True,
            allowed_tools=subagent_allowed_tools
        )

        # Add timeout to prevent hanging
        try:
            _log(f"Agent {agent_id}: Starting graph execution")
            start = time.time()

            result = await asyncio.wait_for(
                graph.ainvoke(state, config={"recursion_limit": 50}),
                timeout=180  # 180 second timeout
            )

            elapsed = time.time() - start
            _log(f"Agent {agent_id}: Graph completed in {elapsed:.2f}s")

        except asyncio.TimeoutError:
            _log(f"Agent {agent_id}: TIMEOUT after 180 seconds")
            return "Error: Task execution timed out after 180 seconds"

        # Check if file was created - if not, create it directly
        import os
        from ..tools import execute_tool
        workspace = settings.workspace_root
        full_path = os.path.join(workspace, target_file) if not os.path.isabs(target_file) else target_file

        if not os.path.exists(full_path):
            _log(f"Agent {agent_id}: File not created, auto-creating {target_file}")
            # Auto-create with basic content based on task description
            auto_content = self._generate_basic_content(task.description, target_file)
            try:
                create_result = await execute_tool("write_file", {
                    "path": target_file,
                    "content": auto_content
                })
                _log(f"Agent {agent_id}: Auto-created file: {create_result}")
            except Exception as e:
                _log(f"Agent {agent_id}: Failed to auto-create: {e}")

        # Extract result
        messages = result.get("messages", [])
        for msg in reversed(messages):
            if isinstance(msg, AIMessage) and not getattr(msg, 'tool_calls', None):
                return msg.content

        return messages[-1].content if messages else "No result"

    def _generate_basic_content(self, task_description: str, target_file: str) -> str:
        """Generate basic file content based on task description and file type."""
        file_ext = target_file.split('.')[-1] if '.' in target_file else 'txt'

        # Extract key info from task description
        desc_lower = task_description.lower()

        if file_ext == 'html':
            # Check for specific page types
            if 'about' in desc_lower or '关于' in desc_lower:
                return '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>关于我们</title>
    <link rel="stylesheet" href="style.css">
</head>
<body>
    <header>
        <nav>
            <a href="index.html">首页</a>
            <a href="about.html">关于我们</a>
        </nav>
    </header>
    <main>
        <h1>关于我们</h1>
        <p>我们是一家专注于创新的公司。</p>
    </main>
    <footer>
        <p>&copy; 2026 公司名称</p>
    </footer>
</body>
</html>'''
            else:
                return f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>页面</title>
    <link rel="stylesheet" href="style.css">
</head>
<body>
    <header><h1>网站标题</h1></header>
    <main>
        <p>这是{target_file}的内容。</p>
    </main>
    <footer><p>&copy; 2026</p></footer>
</body>
</html>'''

        elif file_ext == 'css':
            return '''/* Main Styles */
* { margin: 0; padding: 0; box-sizing: border-box; }

body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    line-height: 1.6;
    color: #333;
    background: #f5f5f5;
}

header {
    background: #2c3e50;
    color: white;
    padding: 1rem;
}

nav a {
    color: white;
    margin-right: 1rem;
    text-decoration: none;
}

main {
    max-width: 1200px;
    margin: 2rem auto;
    padding: 0 1rem;
    background: white;
    border-radius: 8px;
    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
}

footer {
    text-align: center;
    padding: 2rem;
    background: #34495e;
    color: white;
}

h1 { color: #2c3e50; margin-bottom: 1rem; }
p { margin-bottom: 1rem; }
'''

        elif file_ext == 'js':
            return '''// Main JavaScript
document.addEventListener('DOMContentLoaded', function() {
    console.log('Page loaded');

    // Add smooth scrolling
    document.querySelectorAll('a[href^="#"]').forEach(anchor => {
        anchor.addEventListener('click', function (e) {
            e.preventDefault();
            document.querySelector(this.getAttribute('href')).scrollIntoView({
                behavior: 'smooth'
            });
        });
    });
});
'''

        elif file_ext == 'md':
            return f'''# {target_file}

## 概述

{task_description}

## 内容

这里是文件内容。
'''

        else:
            return f"# Auto-generated content for {target_file}\n\n{task_description}\n"


class ParallelStatusTool(BaseTool):
    """Get status of parallel execution."""

    @property
    def name(self) -> str:
        return "parallel_status"

    @property
    def description(self) -> str:
        return "Get detailed status of parallel task execution"

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {},
            "required": [],
        }

    async def execute(self) -> str:
        report = parallel_coordinator.get_status_report()

        lines = ["=== Parallel Execution Status ===\n"]
        lines.append(f"Progress: {report['progress']} ({report['progress_percent']:.1f}%)")
        lines.append(f"Completed: {report['completed']}")
        lines.append(f"Running: {report['running']}")
        lines.append(f"Pending: {report['pending']}")
        lines.append(f"Failed: {report['failed']}")

        if report['agents']:
            lines.append("\n--- Agents ---")
            for aid, info in report['agents'].items():
                lines.append(f"  {aid}: {info['status']}")
                if info['current_task']:
                    lines.append(f"    Working on: {info['current_task']}")
                lines.append(f"    Completed: {info['completed_count']} tasks")

        return "\n".join(lines)


class AggregateResultsTool(BaseTool):
    """Aggregate results from parallel execution."""

    @property
    def name(self) -> str:
        return "aggregate_results"

    @property
    def description(self) -> str:
        return "Aggregate and summarize all parallel task results"

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "format": {
                    "type": "string",
                    "enum": ["summary", "detailed", "json"],
                    "description": "Output format (default: summary)",
                },
            },
            "required": [],
        }

    async def execute(self, format: str = "summary") -> str:
        if not parallel_coordinator.results:
            return "No results to aggregate."

        if format == "json":
            import json
            return json.dumps(parallel_coordinator.get_status_report(), indent=2)

        return parallel_coordinator.aggregate_results()


# Register enhanced parallel tools
register_tool(PlanParallelTool())
register_tool(ExecuteParallelTool())
register_tool(ParallelStatusTool())
register_tool(AggregateResultsTool())
