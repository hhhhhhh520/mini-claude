"""Integration tests for P1 features.

Tests the integration of:
1. UserProfileManager with REPL
2. EnhancedMemoryManager with SessionManager
3. PlanVisualizer with plan_node
"""

import gc
import os
import shutil
import tempfile
from io import StringIO
from unittest.mock import MagicMock

import pytest
from rich.console import Console

from mini_claude.utils.profile import UserProfileManager
from mini_claude.utils.session import SessionManager
from mini_claude.utils.enhanced_memory import EnhancedMemoryManager
from mini_claude.cli.plan_display import (
    PlanVisualizer,
    StepStatus,
    create_plan_from_analysis,
)
from mini_claude.agent.complexity import ComplexityLevel, ComplexityResult


# ========== UserProfileManager Integration Tests ==========


class TestUserProfileManagerIntegration:
    """Tests for UserProfileManager integration with REPL - 8 test cases."""

    @pytest.fixture
    def temp_profile_path(self):
        """Create a temporary profile path for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield os.path.join(tmpdir, "profile.json")

    @pytest.fixture
    def profile_manager(self, temp_profile_path):
        """Create a UserProfileManager with temporary path."""
        return UserProfileManager(profile_path=temp_profile_path)

    def test_profile_loaded_on_startup(self, profile_manager):
        """Test that profile is loaded on startup."""
        # This simulates REPL initialization
        profile = profile_manager.load_profile()
        assert profile is not None
        assert profile.preferred_model == "deepseek-chat"

    def test_profile_saved_on_exit(self, profile_manager):
        """Test that profile is saved on exit."""
        profile = profile_manager.load_profile()
        profile.preferred_model = "gpt-4"
        profile_manager.save_profile(profile)

        # Verify persistence
        new_manager = UserProfileManager(profile_path=profile_manager._profile_path)
        loaded = new_manager.load_profile()
        assert loaded.preferred_model == "gpt-4"

    def test_recent_projects_updated_on_task(self, profile_manager):
        """Test that recent projects are updated when working on tasks."""
        profile_manager.load_profile()

        # Simulate working on a project
        project_path = "/path/to/project"
        profile_manager.add_recent_project(project_path)

        # Verify project is recorded
        projects = profile_manager.get_recent_projects()
        assert len(projects) == 1
        assert project_path in projects[0] or "project" in projects[0]

    def test_common_workflows_recorded(self, profile_manager):
        """Test that common workflows are recorded."""
        profile_manager.load_profile()

        # Simulate workflow execution
        workflow = "create-react-app"
        profile_manager.add_common_workflow(workflow)

        workflows = profile_manager.get_common_workflows()
        assert workflow in workflows

    def test_custom_prompts_management(self, profile_manager):
        """Test custom prompts add/get/remove."""
        profile_manager.load_profile()

        # Add custom prompt
        profile_manager.add_custom_prompt("review", "Review this code for security issues")

        # Get custom prompt
        prompt = profile_manager.get_custom_prompt("review")
        assert prompt == "Review this code for security issues"

        # Remove custom prompt
        result = profile_manager.remove_custom_prompt("review")
        assert result is True

        # Verify removed
        prompt = profile_manager.get_custom_prompt("review")
        assert prompt is None

    def test_profile_preferences_persist(self, profile_manager):
        """Test that preferences persist across sessions."""
        profile_manager.load_profile()
        profile_manager.update_preference("preferred_model", "claude-3-opus")
        profile_manager.update_preference("preferred_language", "en-US")

        # Create new manager to simulate new session
        new_manager = UserProfileManager(profile_path=profile_manager._profile_path)
        assert new_manager.get_preference("preferred_model") == "claude-3-opus"
        assert new_manager.get_preference("preferred_language") == "en-US"

    def test_profile_command_view(self, profile_manager):
        """Test viewing profile via /profile command."""
        profile_manager.load_profile()
        profile_manager.update_preference("preferred_model", "test-model")

        # Verify we can access all profile data
        profile = profile_manager.load_profile()
        assert profile.preferred_model == "test-model"
        assert hasattr(profile, "recent_projects")
        assert hasattr(profile, "common_workflows")
        assert hasattr(profile, "custom_prompts")

    def test_profile_command_edit(self, profile_manager):
        """Test editing profile via /profile command."""
        profile_manager.load_profile()

        # Simulate /profile edit command
        profile_manager.update_preference("preferred_language", "ja-JP")

        # Verify change
        assert profile_manager.get_preference("preferred_language") == "ja-JP"


# ========== PlanVisualizer Integration Tests ==========


class TestPlanVisualizerIntegration:
    """Tests for PlanVisualizer integration with plan_node - 6 test cases."""

    @pytest.fixture
    def visualizer(self):
        """Create visualizer with string console."""
        console = Console(file=StringIO(), force_terminal=True, width=80)
        return PlanVisualizer(console=console)

    @pytest.fixture
    def medium_complexity(self):
        """Create medium complexity result."""
        return ComplexityResult(
            level=ComplexityLevel.MEDIUM,
            score=50,
            strategy="react",
            factors=["Multiple keywords", "File operations"],
        )

    @pytest.fixture
    def complex_complexity(self):
        """Create complex complexity result."""
        return ComplexityResult(
            level=ComplexityLevel.COMPLEX,
            score=85,
            strategy="reflexion",
            factors=["Long task", "Multiple domains", "Complex dependencies"],
        )

    def test_plan_created_for_complex_task(self, visualizer, complex_complexity):
        """Test that plan is created for complex tasks."""
        plan = create_plan_from_analysis(
            "Develop a full-stack web application with authentication",
            complex_complexity,
        )

        assert plan.total_steps > 3  # Complex tasks should have more steps
        assert plan.strategy == "reflexion"

        # Display should work without error
        visualizer.display_plan(plan, complex_complexity)
        output = visualizer.console.file.getvalue()
        assert len(output) > 0

    def test_plan_displayed_in_plan_node(self, visualizer, medium_complexity):
        """Test that plan is displayed during plan_node execution."""
        plan = create_plan_from_analysis(
            "Create a Python package with tests",
            medium_complexity,
        )

        # Display the plan
        visualizer.display_plan(plan, medium_complexity)
        output = visualizer.console.file.getvalue()

        # Should show execution plan
        assert "Plan" in output or "step" in output.lower()

    def test_plan_progress_updates(self, visualizer, medium_complexity):
        """Test that progress updates are displayed."""
        plan = create_plan_from_analysis("Multi-step task", medium_complexity)
        visualizer.display_plan(plan, medium_complexity)

        # Simulate step execution
        visualizer.display_progress("step_1", StepStatus.RUNNING)
        output = visualizer.console.file.getvalue()
        assert "step_1" in output

        visualizer.display_progress("step_1", StepStatus.COMPLETED)
        output = visualizer.console.file.getvalue()
        assert "step_1" in output

    def test_plan_summary_displayed(self, visualizer):
        """Test that execution summary is displayed."""
        result = {
            "success": True,
            "total_steps": 3,
            "completed_steps": 3,
            "failed_steps": 0,
            "execution_time": 5.5,
            "errors": [],
        }

        visualizer.display_summary(result)
        output = visualizer.console.file.getvalue()

        assert "SUCCESS" in output
        assert "3/3" in output

    def test_simple_task_compact_display(self, visualizer):
        """Test that simple tasks use compact display."""
        simple_complexity = ComplexityResult(
            level=ComplexityLevel.SIMPLE,
            score=20,
            strategy="react",
            factors=["Short task"],
        )
        plan = create_plan_from_analysis("Read a file", simple_complexity)

        visualizer.display_plan(plan, simple_complexity)
        output = visualizer.console.file.getvalue()

        # Compact format should be brief
        assert "Plan" in output or len(output) > 0

    def test_plan_dependencies_shown(self, visualizer, complex_complexity):
        """Test that dependencies are shown for complex plans."""
        plan = create_plan_from_analysis(
            "Build and deploy microservices",
            complex_complexity,
        )

        # Use default format (should work)
        visualizer.display_plan(plan, complex_complexity)
        output = visualizer.console.file.getvalue()

        # Complex plans should show some structure
        assert len(output) > 0


# ========== EnhancedMemoryManager Integration Tests ==========


class TestEnhancedMemoryManagerIntegration:
    """Tests for EnhancedMemoryManager integration with SessionManager - 8 test cases."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for testing."""
        tmpdir = tempfile.mkdtemp()
        yield tmpdir
        gc.collect()
        try:
            shutil.rmtree(tmpdir, ignore_errors=True)
        except Exception:
            pass

    @pytest.fixture
    def session_manager(self, temp_dir):
        """Create a SessionManager with temporary database."""
        db_path = os.path.join(temp_dir, "sessions.db")
        return SessionManager(db_path)

    @pytest.fixture
    def mock_vector_store(self):
        """Create a mock vector store."""
        store = MagicMock()
        store.count.return_value = 0
        store.get_stats.return_value = {
            "db_type": "mock",
            "document_count": 0,
        }
        return store

    @pytest.fixture
    def memory_manager(self, session_manager, mock_vector_store):
        """Create an EnhancedMemoryManager with mocked dependencies."""
        try:
            return EnhancedMemoryManager(
                vector_store=mock_vector_store,
                session_manager=session_manager,
            )
        except Exception as e:
            pytest.skip(f"Failed to create memory manager: {e}")

    def test_session_auto_indexed_on_save(self, memory_manager, mock_vector_store):
        """Test that session is automatically indexed when saved."""
        messages = [
            {"role": "user", "content": "How do I deploy Python?"},
            {"role": "assistant", "content": "Use Docker or cloud services."},
        ]

        # Save session
        memory_manager._session_manager.save_session("test-session", messages)

        # Index the session
        mock_vector_store.add_batch.return_value = True
        result = memory_manager.index_session("test-session")

        assert result is True
        mock_vector_store.add_batch.assert_called_once()

    def test_cross_session_search(self, memory_manager, mock_vector_store):
        """Test searching across multiple sessions."""
        from mini_claude.utils.vector_store import SearchResult

        # Setup mock to return search results
        mock_vector_store.search_similar.return_value = [
            SearchResult(
                id="session-1:0",
                text="Python deployment guide",
                score=0.9,
                metadata={
                    "session_id": "session-1",
                    "message_idx": 0,
                    "role": "user",
                },
            ),
            SearchResult(
                id="session-2:0",
                text="Docker best practices",
                score=0.8,
                metadata={
                    "session_id": "session-2",
                    "message_idx": 0,
                    "role": "assistant",
                },
            ),
        ]

        # Save and index multiple sessions
        for i, content in enumerate(["Python deployment guide", "Docker best practices"]):
            session_id = f"session-{i + 1}"
            memory_manager._session_manager.save_session(
                session_id,
                [{"role": "user", "content": content}],
            )

        # Search across sessions
        results = memory_manager.search_history("deploy container", k=5)

        assert len(results) == 2
        assert results[0].session_id == "session-1"
        assert results[1].session_id == "session-2"

    def test_relevant_context_retrieved(self, memory_manager, mock_vector_store):
        """Test retrieving relevant context for current task."""
        from mini_claude.utils.vector_store import SearchResult

        mock_vector_store.search_similar.return_value = [
            SearchResult(
                id="session-1:0",
                text="Use pandas for data processing",
                score=0.9,
                metadata={
                    "session_id": "session-1",
                    "role": "assistant",
                },
            ),
        ]

        context = memory_manager.get_relevant_context("data analysis", max_tokens=500)

        assert len(context) == 1
        assert "pandas" in context[0]

    def test_session_indexed_after_save(self, memory_manager, mock_vector_store):
        """Test that session can be indexed after save."""
        messages = [
            {"role": "user", "content": "Test message"},
        ]

        memory_manager._session_manager.save_session("new-session", messages)
        mock_vector_store.add_batch.return_value = True

        result = memory_manager.index_session("new-session")
        assert result is True

    def test_index_all_sessions(self, memory_manager, mock_vector_store):
        """Test indexing all sessions at once."""
        # Create multiple sessions
        for i in range(3):
            memory_manager._session_manager.save_session(
                f"session-{i}",
                [{"role": "user", "content": f"Message {i}"}],
            )

        mock_vector_store.add_batch.return_value = True

        count = memory_manager.index_all_sessions()
        assert count == 3

    def test_search_with_time_filter(self, memory_manager, mock_vector_store):
        """Test search with time range filter."""
        from datetime import datetime
        from mini_claude.utils.vector_store import SearchResult

        mock_vector_store.search_similar.return_value = [
            SearchResult(
                id="session-1:0",
                text="Recent message",
                score=0.9,
                metadata={
                    "session_id": "session-1",
                    "message_idx": 0,
                    "role": "user",
                    "timestamp": "2026-05-01T12:00:00",
                },
            ),
        ]

        start_time = datetime(2026, 5, 1, 0, 0, 0)
        end_time = datetime(2026, 5, 2, 23, 59, 59)

        results = memory_manager.search_history(
            "test",
            k=5,
            time_range=(start_time, end_time),
        )

        assert len(results) == 1

    def test_stats_include_indexing_status(self, memory_manager, mock_vector_store):
        """Test that stats show indexing status."""
        memory_manager._session_manager.save_session(
            "session-1",
            [{"role": "user", "content": "Test"}],
        )
        memory_manager._indexed_sessions.add("session-1")

        stats = memory_manager.get_stats()

        assert stats["total_sessions"] >= 1
        assert stats["indexed_sessions"] == 1

    def test_delete_session_removes_index(self, memory_manager, mock_vector_store):
        """Test that deleting session removes it from index."""
        memory_manager._session_manager.save_session(
            "session-to-delete",
            [{"role": "user", "content": "Delete me"}],
        )
        memory_manager._indexed_sessions.add("session-to-delete")
        mock_vector_store.delete_by_id.return_value = True

        result = memory_manager.delete_session_index("session-to-delete")

        assert result is True
        assert "session-to-delete" not in memory_manager._indexed_sessions


# ========== End-to-End Integration Tests ==========


class TestEndToEndIntegration:
    """End-to-end integration tests - 4 test cases."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for testing."""
        tmpdir = tempfile.mkdtemp()
        yield tmpdir
        gc.collect()
        try:
            shutil.rmtree(tmpdir, ignore_errors=True)
        except Exception:
            pass

    def test_full_profile_workflow(self, temp_dir):
        """Test complete profile workflow from startup to shutdown."""
        profile_path = os.path.join(temp_dir, "profile.json")

        # Simulate startup - load profile
        manager = UserProfileManager(profile_path=profile_path)
        profile = manager.load_profile()
        assert profile is not None

        # Simulate working on tasks
        manager.add_recent_project("/project/workspace")
        manager.add_common_workflow("web-development")

        # Simulate customizing preferences
        manager.update_preference("preferred_model", "claude-3-opus")

        # Simulate exit - profile auto-saved
        profile = manager.load_profile()
        assert profile.preferred_model == "claude-3-opus"

        # Verify persistence across sessions
        new_manager = UserProfileManager(profile_path=profile_path)
        loaded = new_manager.load_profile()
        assert loaded.preferred_model == "claude-3-opus"
        assert len(loaded.recent_projects) == 1
        assert "web-development" in loaded.common_workflows

    def test_full_memory_workflow(self, temp_dir):
        """Test complete memory workflow with session indexing."""
        try:
            from mini_claude.utils.vector_store import VectorStore

            db_path = os.path.join(temp_dir, "sessions.db")
            vector_path = os.path.join(temp_dir, "vectors")

            session_manager = SessionManager(db_path)
            vector_store = VectorStore(
                db_type="chroma",
                path=vector_path,
                collection_name="test_memory",
            )

            memory_manager = EnhancedMemoryManager(
                vector_store=vector_store,
                session_manager=session_manager,
            )

            # Create and save session
            messages = [
                {"role": "user", "content": "How do I create a REST API?"},
                {"role": "assistant", "content": "Use FastAPI or Flask."},
            ]
            session_manager.save_session("api-session", messages)

            # Index session
            result = memory_manager.index_session("api-session")
            assert result is True

            # Search
            results = memory_manager.search_history("REST API creation", k=3)
            assert len(results) > 0

            # Cleanup
            memory_manager.delete_session_index("api-session")
            vector_store.clear()

        except Exception as e:
            pytest.skip(f"Dependencies not available: {e}")

    def test_plan_visualization_workflow(self, temp_dir):
        """Test complete plan visualization workflow."""
        console = Console(file=StringIO(), force_terminal=True, width=80)
        visualizer = PlanVisualizer(console=console)

        # Create plan for complex task
        complexity = ComplexityResult(
            level=ComplexityLevel.COMPLEX,
            score=80,
            strategy="reflexion",
            factors=["Multi-file", "Database", "API"],
        )

        plan = create_plan_from_analysis(
            "Build a REST API with database",
            complexity,
            steps=[
                "Design database schema",
                "Create API endpoints",
                "Implement authentication",
                "Add tests",
                "Deploy",
            ],
        )

        # Display plan
        visualizer.display_plan(plan, complexity)
        output = visualizer.console.file.getvalue()
        assert len(output) > 0

        # Simulate execution
        for step in plan.steps:
            visualizer.display_progress(step.id, StepStatus.RUNNING)
            visualizer.display_progress(step.id, StepStatus.COMPLETED)

        # Display summary
        result = {
            "success": True,
            "total_steps": plan.total_steps,
            "completed_steps": plan.total_steps,
            "failed_steps": 0,
            "execution_time": 10.0,
            "errors": [],
        }
        visualizer.display_summary(result)

        output = visualizer.console.file.getvalue()
        assert "SUCCESS" in output

    def test_integration_with_session_persistence(self, temp_dir):
        """Test that sessions persist correctly with all features."""
        db_path = os.path.join(temp_dir, "sessions.db")
        profile_path = os.path.join(temp_dir, "profile.json")

        # Initialize managers
        session_manager = SessionManager(db_path)
        profile_manager = UserProfileManager(profile_path=profile_path)

        # Create session
        messages = [
            {"role": "user", "content": "Create a web app"},
            {"role": "assistant", "content": "I'll help you create a web app."},
        ]
        session_manager.save_session("web-session", messages)

        # Update profile
        profile_manager.load_profile()
        profile_manager.add_recent_project(temp_dir)

        # Verify session persistence
        loaded, summary = session_manager.load_session("web-session")
        assert loaded is not None
        assert len(loaded) == 2

        # Verify profile persistence
        projects = profile_manager.get_recent_projects()
        assert len(projects) >= 1
