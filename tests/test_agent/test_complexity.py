"""Tests for task complexity analyzer."""

import pytest
from mini_claude.agent.complexity import (
    ComplexityLevel,
    ComplexityResult,
    TaskComplexityAnalyzer,
    analyze_task_complexity,
)


class TestComplexityLevel:
    """Tests for ComplexityLevel enum."""

    def test_level_values(self):
        """Test enum values."""
        assert ComplexityLevel.SIMPLE.value == "simple"
        assert ComplexityLevel.MEDIUM.value == "medium"
        assert ComplexityLevel.COMPLEX.value == "complex"


class TestComplexityResult:
    """Tests for ComplexityResult dataclass."""

    def test_to_dict(self):
        """Test serialization."""
        result = ComplexityResult(
            level=ComplexityLevel.SIMPLE,
            score=25,
            strategy="react",
            factors=["Short task (<50 chars)"],
            details={"length_score": 5},
        )

        d = result.to_dict()
        assert d["level"] == "simple"
        assert d["score"] == 25
        assert d["strategy"] == "react"
        assert d["factors"] == ["Short task (<50 chars)"]
        assert d["details"] == {"length_score": 5}


class TestTaskComplexityAnalyzer:
    """Tests for TaskComplexityAnalyzer class."""

    def test_initial_state(self):
        """Test default initialization."""
        analyzer = TaskComplexityAnalyzer()

        assert analyzer.simple_threshold == 30
        assert analyzer.medium_threshold == 70

    def test_custom_thresholds(self):
        """Test custom thresholds."""
        analyzer = TaskComplexityAnalyzer({
            "simple_threshold": 20,
            "medium_threshold": 50,
        })

        assert analyzer.simple_threshold == 20
        assert analyzer.medium_threshold == 50

    def test_analyze_simple_task(self):
        """Test analyzing a simple task."""
        analyzer = TaskComplexityAnalyzer()
        result = analyzer.analyze("Fix typo in README")

        assert result.level == ComplexityLevel.SIMPLE
        assert result.score <= 30
        assert result.strategy == "react"

    def test_analyze_medium_task(self):
        """Test analyzing a medium complexity task."""
        analyzer = TaskComplexityAnalyzer()
        result = analyzer.analyze(
            "Optimize the database query performance for the user dashboard"
        )

        assert result.level in [ComplexityLevel.MEDIUM, ComplexityLevel.COMPLEX]
        assert "optimize" in str(result.factors).lower() or "优化" in str(result.factors)

    def test_analyze_complex_task(self):
        """Test analyzing a complex task."""
        analyzer = TaskComplexityAnalyzer()
        result = analyzer.analyze(
            "Develop a new payment integration system with multiple payment gateways, "
            "including fraud detection, transaction logging, and refund handling"
        )

        assert result.level == ComplexityLevel.COMPLEX
        assert result.strategy == "reflexion"
        assert result.score > 70

    def test_keyword_detection(self):
        """Test keyword detection and scoring."""
        analyzer = TaskComplexityAnalyzer()

        # Fix keyword
        result1 = analyzer.analyze("Fix the bug")
        result2 = analyzer.analyze("Develop new feature")

        # "develop" should score higher than "fix"
        assert result2.details["keyword_score"] > result1.details["keyword_score"]

    def test_domain_detection(self):
        """Test domain detection and scoring."""
        analyzer = TaskComplexityAnalyzer()

        result = analyzer.analyze("Implement payment processing")
        assert result.details["domain_score"] > 0
        assert any("payment" in f.lower() for f in result.factors)

    def test_risk_detection(self):
        """Test risk indicator detection."""
        analyzer = TaskComplexityAnalyzer()

        result = analyzer.analyze("Fix critical production bug")
        assert result.details["risk_score"] > 0
        assert any("critical" in f.lower() or "production" in f.lower() for f in result.factors)

    def test_length_analysis(self):
        """Test task length analysis."""
        analyzer = TaskComplexityAnalyzer()

        # Short task (<50 chars)
        short_result = analyzer.analyze("Fix bug")
        assert short_result.details["length_score"] == 5

        # Medium task (50-200 chars)
        medium_task = "Fix the authentication bug in the login module and update the tests"
        medium_result = analyzer.analyze(medium_task)
        assert len(medium_task) >= 50
        assert medium_result.details["length_score"] == 15

        # Long task (>200 chars)
        long_task = (
            "Implement a comprehensive user authentication system with OAuth2, "
            "JWT tokens, refresh token rotation, and multi-factor authentication support "
            "including SMS verification, email verification, and hardware key support"
        )
        assert len(long_task) > 200
        long_result = analyzer.analyze(long_task)
        assert long_result.details["length_score"] == 30

    def test_context_file_count(self):
        """Test context-based analysis with file count."""
        analyzer = TaskComplexityAnalyzer()

        # Single file
        result1 = analyzer.analyze("Fix bug", context={"file_count": 1})
        assert result1.details["context_score"] == 5

        # Multiple files
        result2 = analyzer.analyze("Fix bug", context={"file_count": 3})
        assert result2.details["context_score"] == 15

        # Many files
        result3 = analyzer.analyze("Fix bug", context={"file_count": 10})
        assert result3.details["context_score"] == 30

    def test_context_file_paths(self):
        """Test context-based analysis with file paths."""
        analyzer = TaskComplexityAnalyzer()

        result = analyzer.analyze(
            "Update imports",
            context={"file_paths": ["a.py", "b.py", "c.py"]}
        )
        assert result.details["context_score"] == 15

    def test_context_production(self):
        """Test production environment context."""
        analyzer = TaskComplexityAnalyzer()

        result = analyzer.analyze(
            "Deploy to production",
            context={"is_production": True}
        )
        assert result.details["context_score"] == 20

    def test_context_no_tests(self):
        """Test no tests context."""
        analyzer = TaskComplexityAnalyzer()

        result = analyzer.analyze(
            "Add new feature",
            context={"has_tests": False}
        )
        assert result.details["context_score"] == 10

    def test_context_dependencies(self):
        """Test dependencies context."""
        analyzer = TaskComplexityAnalyzer()

        result = analyzer.analyze(
            "Update API",
            context={"dependencies": ["auth", "db", "cache", "queue"]}
        )
        assert result.details["context_score"] == 15

    def test_get_strategy(self):
        """Test strategy mapping."""
        analyzer = TaskComplexityAnalyzer()

        assert analyzer.get_strategy(ComplexityLevel.SIMPLE) == "react"
        assert analyzer.get_strategy(ComplexityLevel.MEDIUM) == "react"
        assert analyzer.get_strategy(ComplexityLevel.COMPLEX) == "reflexion"

    def test_get_max_iterations(self):
        """Test max iterations mapping."""
        analyzer = TaskComplexityAnalyzer()

        assert analyzer.get_max_iterations(ComplexityLevel.SIMPLE) == 5
        assert analyzer.get_max_iterations(ComplexityLevel.MEDIUM) == 10
        assert analyzer.get_max_iterations(ComplexityLevel.COMPLEX) == 15

    def test_custom_keywords(self):
        """Test custom keyword configuration."""
        analyzer = TaskComplexityAnalyzer({
            "custom_keywords": {
                "super_complex": 100,
            }
        })

        result = analyzer.analyze("This is super_complex task")
        assert result.details["keyword_score"] == 100

    def test_custom_domains(self):
        """Test custom domain configuration."""
        analyzer = TaskComplexityAnalyzer({
            "custom_domains": {
                "blockchain": 50,
            }
        })

        result = analyzer.analyze("Build blockchain system")
        # Only blockchain should match as domain, "build" is a keyword
        assert result.details["domain_score"] >= 50
        assert any("blockchain" in f for f in result.factors)

    def test_chinese_keywords(self):
        """Test Chinese keyword detection."""
        analyzer = TaskComplexityAnalyzer()

        result = analyzer.analyze("修复登录bug")
        assert result.details["keyword_score"] == 10  # "修复" = fix

    def test_chinese_domains(self):
        """Test Chinese domain detection."""
        analyzer = TaskComplexityAnalyzer()

        result = analyzer.analyze("实现支付功能")
        assert result.details["domain_score"] == 40  # "支付" = payment

    def test_combined_factors(self):
        """Test combined factor analysis."""
        analyzer = TaskComplexityAnalyzer()

        result = analyzer.analyze(
            "重构数据库架构以提高性能",
            context={"file_count": 5, "is_production": True}
        )

        # Should have keyword score (重构=30), domain score (数据库=20, 性能=20)
        # and context score (15 for files, 20 for production)
        assert result.details["keyword_score"] > 0
        assert result.details["domain_score"] > 0
        assert result.details["context_score"] > 0

    def test_score_boundary_simple_medium(self):
        """Test score boundary between SIMPLE and MEDIUM."""
        analyzer = TaskComplexityAnalyzer()

        # Exactly at simple threshold
        result = analyzer.analyze("Fix bug in code")
        assert result.level == ComplexityLevel.SIMPLE
        assert result.score <= 30

    def test_score_boundary_medium_complex(self):
        """Test score boundary between MEDIUM and COMPLEX."""
        analyzer = TaskComplexityAnalyzer()

        # Task that should be COMPLEX
        result = analyzer.analyze(
            "Develop new payment system with security features",
            context={"file_count": 8, "is_production": True}
        )
        assert result.level == ComplexityLevel.COMPLEX


class TestAnalyzeTaskComplexity:
    """Tests for convenience function."""

    def test_convenience_function(self):
        """Test analyze_task_complexity convenience function."""
        result = analyze_task_complexity("Fix typo")

        assert isinstance(result, ComplexityResult)
        assert result.level == ComplexityLevel.SIMPLE

    def test_with_context(self):
        """Test convenience function with context."""
        result = analyze_task_complexity(
            "Update module",
            context={"file_count": 3}
        )

        assert isinstance(result, ComplexityResult)
        assert result.details["context_score"] == 15
