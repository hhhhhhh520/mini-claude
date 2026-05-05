"""Task complexity analyzer for intelligent strategy selection.

This module provides TaskComplexityAnalyzer to evaluate task complexity
and recommend appropriate execution strategies.

Complexity Levels:
- SIMPLE (0-30): Direct execution with ReAct
- MEDIUM (31-70): Planned execution with ReAct
- COMPLEX (71+): Reflective execution with Reflexion

Analysis Dimensions:
1. Keyword analysis: fix(+10), optimize(+20), develop(+50), refactor(+30)
2. Task length: short(<50 chars, +5), medium(50-200, +15), long(>200, +30)
3. File count: single(+5), multiple(+15), cross-project(+30)
4. Technical domain: database(+20), security(+25), payment(+40)
"""

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set

from mini_claude.utils.logger import get_logger

logger = get_logger(__name__)


class ComplexityLevel(str, Enum):
    """Task complexity levels."""
    SIMPLE = "simple"
    MEDIUM = "medium"
    COMPLEX = "complex"


@dataclass
class ComplexityResult:
    """Result of complexity analysis.

    Attributes:
        level: Complexity level (SIMPLE, MEDIUM, COMPLEX)
        score: Numerical complexity score (0-100+)
        strategy: Recommended execution strategy
        factors: List of factors that contributed to the score
        details: Detailed breakdown by dimension
    """
    level: ComplexityLevel
    score: int
    strategy: str
    factors: List[str] = field(default_factory=list)
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "level": self.level.value,
            "score": self.score,
            "strategy": self.strategy,
            "factors": self.factors,
            "details": self.details,
        }


class TaskComplexityAnalyzer:
    """Analyzes task complexity and recommends execution strategy.

    This analyzer evaluates tasks across multiple dimensions to determine
    the appropriate execution strategy (simple react, planned react, or reflexion).

    Example:
        analyzer = TaskComplexityAnalyzer()
        result = analyzer.analyze("Fix the login bug in auth.py")
        print(result.level)  # ComplexityLevel.SIMPLE
        print(result.strategy)  # "react"
    """

    # Keyword scores - higher means more complex
    KEYWORD_SCORES: Dict[str, int] = {
        # Simple operations
        "fix": 10,
        "修复": 10,
        "resolve": 10,
        "解决": 10,
        "update": 10,
        "更新": 10,
        "change": 10,
        "修改": 10,

        # Medium complexity
        "optimize": 20,
        "优化": 20,
        "improve": 20,
        "改进": 20,
        "enhance": 20,
        "增强": 20,
        "refactor": 30,
        "重构": 30,
        "redesign": 30,
        "重新设计": 30,

        # Complex operations
        "develop": 50,
        "开发": 50,
        "implement": 50,
        "实现": 50,
        "create": 40,
        "创建": 40,
        "build": 40,
        "构建": 40,
        "migrate": 35,
        "迁移": 35,
        "integrate": 35,
        "集成": 35,
    }

    # Technical domain scores
    DOMAIN_SCORES: Dict[str, int] = {
        # Infrastructure
        "deploy": 20,
        "部署": 20,
        "infrastructure": 20,
        "基础设施": 20,
        "docker": 15,
        "kubernetes": 20,
        "k8s": 20,

        # Data
        "database": 20,
        "数据库": 20,
        "sql": 15,
        "migration": 20,
        "数据迁移": 20,
        "query": 10,
        "查询": 10,

        # Security
        "security": 25,
        "安全": 25,
        "auth": 20,
        "认证": 20,
        "authentication": 20,
        "授权": 20,
        "authorization": 20,
        "encryption": 25,
        "加密": 25,
        "vulnerability": 30,
        "漏洞": 30,

        # High-risk domains
        "payment": 40,
        "支付": 40,
        "transaction": 35,
        "交易": 35,
        "financial": 35,
        "金融": 35,

        # AI/ML
        "model": 25,
        "模型": 25,
        "training": 30,
        "训练": 30,
        "ml": 25,
        "ai": 25,
        "machine learning": 25,
        "机器学习": 25,

        # Performance
        "performance": 20,
        "性能": 20,
        "scale": 20,
        "扩展": 20,
        "scalability": 20,
        "可扩展": 20,

        # Architecture
        "architecture": 30,
        "架构": 30,
        "microservice": 25,
        "微服务": 25,
        "api": 15,
        "interface": 15,
        "接口": 15,
    }

    # Risk indicators that add complexity
    RISK_INDICATORS: Set[str] = {
        "critical", "关键",
        "urgent", "紧急",
        "production", "生产",
        "live", "在线",
        "breaking", "破坏性",
        "deprecated", "废弃",
        "legacy", "遗留",
    }

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize the complexity analyzer.

        Args:
            config: Configuration options:
                - simple_threshold: Upper bound for SIMPLE (default: 30)
                - medium_threshold: Upper bound for MEDIUM (default: 70)
                - custom_keywords: Additional keyword scores
                - custom_domains: Additional domain scores
        """
        config = config or {}
        self.simple_threshold = config.get("simple_threshold", 30)
        self.medium_threshold = config.get("medium_threshold", 70)

        # Merge custom keywords/domains
        self.keyword_scores = {**self.KEYWORD_SCORES}
        if custom_keywords := config.get("custom_keywords"):
            self.keyword_scores.update(custom_keywords)

        self.domain_scores = {**self.DOMAIN_SCORES}
        if custom_domains := config.get("custom_domains"):
            self.domain_scores.update(custom_domains)

    def analyze(
        self,
        task: str,
        context: Optional[Dict[str, Any]] = None
    ) -> ComplexityResult:
        """Analyze task complexity.

        Args:
            task: User task description
            context: Additional context information:
                - file_count: Number of files involved
                - file_paths: List of file paths
                - dependencies: List of dependencies
                - has_tests: Whether tests exist
                - is_production: Whether affects production

        Returns:
            ComplexityResult with level, score, strategy, and details
        """
        context = context or {}
        factors: List[str] = []
        details: Dict[str, Any] = {}

        # 1. Analyze task length
        length_score, length_factor = self._analyze_length(task)
        if length_factor:
            factors.append(length_factor)
        details["length_score"] = length_score
        details["task_length"] = len(task)

        # 2. Analyze keywords
        keyword_score, keyword_factors = self._analyze_keywords(task)
        factors.extend(keyword_factors)
        details["keyword_score"] = keyword_score
        details["matched_keywords"] = keyword_factors

        # 3. Analyze technical domains
        domain_score, domain_factors = self._analyze_domains(task)
        factors.extend(domain_factors)
        details["domain_score"] = domain_score
        details["matched_domains"] = domain_factors

        # 4. Analyze risk indicators
        risk_score, risk_factors = self._analyze_risks(task)
        factors.extend(risk_factors)
        details["risk_score"] = risk_score
        details["matched_risks"] = risk_factors

        # 5. Analyze context (file count, etc.)
        context_score, context_factors = self._analyze_context(context)
        factors.extend(context_factors)
        details["context_score"] = context_score

        # Calculate total score
        total_score = (
            length_score +
            keyword_score +
            domain_score +
            risk_score +
            context_score
        )

        # Determine level and strategy
        level = self._get_level(total_score)
        strategy = self.get_strategy(level)

        details["total_score"] = total_score

        logger.debug(
            "Task complexity analyzed",
            task=task[:50] + "..." if len(task) > 50 else task,
            score=total_score,
            complexity_level=level.value,
            strategy=strategy,
        )

        return ComplexityResult(
            level=level,
            score=total_score,
            strategy=strategy,
            factors=factors,
            details=details,
        )

    def get_strategy(self, level: ComplexityLevel) -> str:
        """Get recommended strategy for a complexity level.

        Args:
            level: Complexity level

        Returns:
            Strategy name: "react" or "reflexion"
        """
        strategy_map = {
            ComplexityLevel.SIMPLE: "react",
            ComplexityLevel.MEDIUM: "react",
            ComplexityLevel.COMPLEX: "reflexion",
        }
        return strategy_map[level]

    def get_max_iterations(self, level: ComplexityLevel) -> int:
        """Get recommended max iterations for a complexity level.

        Args:
            level: Complexity level

        Returns:
            Maximum number of iterations
        """
        iteration_map = {
            ComplexityLevel.SIMPLE: 5,
            ComplexityLevel.MEDIUM: 10,
            ComplexityLevel.COMPLEX: 15,
        }
        return iteration_map[level]

    def _analyze_length(self, task: str) -> tuple[int, Optional[str]]:
        """Analyze task length.

        Returns:
            Tuple of (score, factor_description)
        """
        length = len(task)

        if length < 50:
            return 5, "Short task (<50 chars)"
        elif length < 200:
            return 15, "Medium task (50-200 chars)"
        else:
            return 30, "Long task (>200 chars)"

    @staticmethod
    def _word_match(word: str, text: str) -> bool:
        """Match word with boundary-aware matching.

        For ASCII-only keywords, uses \\b word boundaries to prevent
        substring false positives (e.g. 'ml' matching inside 'html').

        For non-ASCII keywords (Chinese, etc.), uses simple substring
        matching since \\b doesn't work with CJK characters.
        """
        if word.isascii():
            return bool(re.search(r'\b' + re.escape(word) + r'\b', text))
        return word in text

    def _analyze_keywords(self, task: str) -> tuple[int, List[str]]:
        """Analyze keywords in task."""
        task_lower = task.lower()
        total_score = 0
        factors: List[str] = []

        for keyword, score in self.keyword_scores.items():
            if self._word_match(keyword.lower(), task_lower):
                total_score += score
                factors.append(f"Keyword '{keyword}' (+{score})")

        return total_score, factors

    def _analyze_domains(self, task: str) -> tuple[int, List[str]]:
        """Analyze technical domains in task."""
        task_lower = task.lower()
        total_score = 0
        factors: List[str] = []

        for domain, score in self.domain_scores.items():
            if self._word_match(domain.lower(), task_lower):
                total_score += score
                factors.append(f"Domain '{domain}' (+{score})")

        return total_score, factors

    def _analyze_risks(self, task: str) -> tuple[int, List[str]]:
        """Analyze risk indicators in task."""
        task_lower = task.lower()
        total_score = 0
        factors: List[str] = []

        for risk in self.RISK_INDICATORS:
            if self._word_match(risk.lower(), task_lower):
                total_score += 15
                factors.append(f"Risk indicator '{risk}' (+15)")

        return total_score, factors

    def _analyze_context(self, context: Dict[str, Any]) -> tuple[int, List[str]]:
        """Analyze context information.

        Returns:
            Tuple of (total_score, list_of_factors)
        """
        total_score = 0
        factors: List[str] = []

        # File count analysis
        file_count = context.get("file_count", 0)
        file_paths = context.get("file_paths", [])

        if not file_count and file_paths:
            file_count = len(file_paths)

        if file_count == 0:
            pass  # No files mentioned
        elif file_count == 1:
            total_score += 5
            factors.append("Single file (+5)")
        elif file_count <= 5:
            total_score += 15
            factors.append(f"Multiple files ({file_count}) (+15)")
        else:
            total_score += 30
            factors.append(f"Many files ({file_count}) (+30)")

        # Cross-project indicator
        if context.get("is_cross_project"):
            total_score += 30
            factors.append("Cross-project change (+30)")

        # Production indicator
        if context.get("is_production"):
            total_score += 20
            factors.append("Production environment (+20)")

        # No existing tests
        if context.get("has_tests") is False:
            total_score += 10
            factors.append("No existing tests (+10)")

        # Dependencies
        dependencies = context.get("dependencies", [])
        if len(dependencies) > 3:
            total_score += 15
            factors.append(f"Multiple dependencies ({len(dependencies)}) (+15)")

        return total_score, factors

    def _get_level(self, score: int) -> ComplexityLevel:
        """Determine complexity level from score.

        Args:
            score: Total complexity score

        Returns:
            ComplexityLevel enum value
        """
        if score <= self.simple_threshold:
            return ComplexityLevel.SIMPLE
        elif score <= self.medium_threshold:
            return ComplexityLevel.MEDIUM
        else:
            return ComplexityLevel.COMPLEX


def analyze_task_complexity(
    task: str,
    context: Optional[Dict[str, Any]] = None
) -> ComplexityResult:
    """Convenience function to analyze task complexity.

    Args:
        task: Task description
        context: Additional context

    Returns:
        ComplexityResult
    """
    analyzer = TaskComplexityAnalyzer()
    return analyzer.analyze(task, context)
