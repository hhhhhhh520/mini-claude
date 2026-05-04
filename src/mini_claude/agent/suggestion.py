"""User operation suggestions engine.

Provides actionable suggestions for various error types.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Dict, Any


class ErrorType(Enum):
    """Error type classification."""
    API_RATE_LIMIT = "api_rate_limit"       # API 限流
    FILE_PERMISSION = "file_permission"      # 文件权限
    NETWORK_TIMEOUT = "network_timeout"      # 网络超时
    TOKEN_EXCEEDED = "token_exceeded"        # Token 超限
    TOOL_FAILURE = "tool_failure"            # 工具失败
    MODEL_ERROR = "model_error"              # 模型错误
    FILE_NOT_FOUND = "file_not_found"        # 文件不存在
    INVALID_PARAMETER = "invalid_parameter"  # 参数无效
    UNKNOWN = "unknown"                      # 未知错误


class Priority(Enum):
    """Suggestion priority level."""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class Suggestion:
    """User operation suggestion.

    Attributes:
        title: Short title for the suggestion
        description: Detailed description
        actions: List of executable actions
        priority: Priority level (high/medium/low)
        command: Optional command to execute
        doc_link: Optional documentation link
    """
    title: str
    description: str
    actions: List[str] = field(default_factory=list)
    priority: Priority = Priority.MEDIUM
    command: Optional[str] = None
    doc_link: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "title": self.title,
            "description": self.description,
            "actions": self.actions,
            "priority": self.priority.value,
            "command": self.command,
            "doc_link": self.doc_link,
        }


class SuggestionEngine:
    """Engine for generating user operation suggestions.

    Analyzes errors and provides specific, actionable suggestions
    in both Chinese and English.
    """

    # Error pattern to ErrorType mapping
    ERROR_PATTERNS = {
        # API Rate Limit patterns
        "rate limit": ErrorType.API_RATE_LIMIT,
        "too many requests": ErrorType.API_RATE_LIMIT,
        "429": ErrorType.API_RATE_LIMIT,
        "quota exceeded": ErrorType.API_RATE_LIMIT,
        "请求频率超限": ErrorType.API_RATE_LIMIT,
        "速率限制": ErrorType.API_RATE_LIMIT,

        # File Permission patterns
        "permission denied": ErrorType.FILE_PERMISSION,
        "permissiondenied": ErrorType.FILE_PERMISSION,  # camel case: PermissionDenied
        "access denied": ErrorType.FILE_PERMISSION,
        "permissionerror": ErrorType.FILE_PERMISSION,
        "权限不足": ErrorType.FILE_PERMISSION,
        "无法访问": ErrorType.FILE_PERMISSION,
        "chmod": ErrorType.FILE_PERMISSION,

        # Network Timeout patterns
        "timeout": ErrorType.NETWORK_TIMEOUT,
        "timed out": ErrorType.NETWORK_TIMEOUT,
        "connection timeout": ErrorType.NETWORK_TIMEOUT,
        "网络超时": ErrorType.NETWORK_TIMEOUT,
        "连接超时": ErrorType.NETWORK_TIMEOUT,
        "asyncio.TimeoutError": ErrorType.NETWORK_TIMEOUT,

        # Token Exceeded patterns
        "token limit": ErrorType.TOKEN_EXCEEDED,
        "context length": ErrorType.TOKEN_EXCEEDED,
        "max tokens": ErrorType.TOKEN_EXCEEDED,
        "token 超限": ErrorType.TOKEN_EXCEEDED,
        "上下文过长": ErrorType.TOKEN_EXCEEDED,
        "token budget exceeded": ErrorType.TOKEN_EXCEEDED,

        # Tool Failure patterns
        "tool error": ErrorType.TOOL_FAILURE,
        "tool failed": ErrorType.TOOL_FAILURE,
        "execution failed": ErrorType.TOOL_FAILURE,
        "工具执行失败": ErrorType.TOOL_FAILURE,
        "工具错误": ErrorType.TOOL_FAILURE,
        "tool execution error": ErrorType.TOOL_FAILURE,

        # Model Error patterns
        "model error": ErrorType.MODEL_ERROR,
        "invalid model": ErrorType.MODEL_ERROR,
        "model not found": ErrorType.MODEL_ERROR,
        "api key": ErrorType.MODEL_ERROR,
        "模型错误": ErrorType.MODEL_ERROR,
        "invalid api key": ErrorType.MODEL_ERROR,
        "authentication": ErrorType.MODEL_ERROR,

        # File Not Found patterns
        "file not found": ErrorType.FILE_NOT_FOUND,
        "no such file": ErrorType.FILE_NOT_FOUND,
        "filenotfounderror": ErrorType.FILE_NOT_FOUND,
        "文件不存在": ErrorType.FILE_NOT_FOUND,
        "找不到文件": ErrorType.FILE_NOT_FOUND,

        # Invalid Parameter patterns
        "invalid parameter": ErrorType.INVALID_PARAMETER,
        "invalid argument": ErrorType.INVALID_PARAMETER,
        "type error": ErrorType.INVALID_PARAMETER,
        "value error": ErrorType.INVALID_PARAMETER,
        "参数错误": ErrorType.INVALID_PARAMETER,
        "参数无效": ErrorType.INVALID_PARAMETER,
    }

    # Suggestions for each error type (Chinese)
    SUGGESTIONS_CN: Dict[ErrorType, List[Suggestion]] = {
        ErrorType.API_RATE_LIMIT: [
            Suggestion(
                title="等待后重试",
                description="API 请求频率超限，等待一段时间后重试",
                actions=[
                    "等待 60 秒后重试",
                    "检查是否有重复请求",
                    "减少请求频率",
                ],
                priority=Priority.HIGH,
                command="/wait 60",
            ),
            Suggestion(
                title="切换备用模型",
                description="切换到备用模型继续执行",
                actions=[
                    "使用 /model 命令切换模型",
                    "推荐模型：deepseek-chat, gpt-4o-mini",
                ],
                priority=Priority.MEDIUM,
                command="/model",
            ),
        ],
        ErrorType.FILE_PERMISSION: [
            Suggestion(
                title="检查文件权限",
                description="当前用户可能没有足够的权限访问文件",
                actions=[
                    "检查文件权限: ls -la <文件路径>",
                    "修改权限: chmod +x <文件路径>",
                    "检查文件所有者: stat <文件路径>",
                ],
                priority=Priority.HIGH,
            ),
            Suggestion(
                title="使用提升权限",
                description="使用管理员权限执行操作",
                actions=[
                    "Windows: 以管理员身份运行",
                    "Linux/Mac: 使用 sudo 命令",
                    "检查当前用户组: groups",
                ],
                priority=Priority.MEDIUM,
            ),
        ],
        ErrorType.NETWORK_TIMEOUT: [
            Suggestion(
                title="检查网络连接",
                description="网络连接可能不稳定或超时",
                actions=[
                    "检查网络连接状态",
                    "尝试 ping api.deepseek.com",
                    "检查代理设置",
                ],
                priority=Priority.HIGH,
            ),
            Suggestion(
                title="增加超时时间",
                description="当前超时时间可能不足",
                actions=[
                    "在配置中增加超时时间",
                    "设置 LLM_TIMEOUT=120",
                ],
                priority=Priority.MEDIUM,
            ),
        ],
        ErrorType.TOKEN_EXCEEDED: [
            Suggestion(
                title="清理对话历史",
                description="对话历史过长，需要清理",
                actions=[
                    "使用 /clear 清理历史",
                    "开始新的对话会话",
                ],
                priority=Priority.HIGH,
                command="/clear",
            ),
            Suggestion(
                title="切换大上下文模型",
                description="切换到支持更大上下文的模型",
                actions=[
                    "推荐模型：claude-3-opus (200K)",
                    "推荐模型：gpt-4-turbo (128K)",
                    "使用 /model 命令切换",
                ],
                priority=Priority.MEDIUM,
                command="/model",
            ),
        ],
        ErrorType.TOOL_FAILURE: [
            Suggestion(
                title="检查工具参数",
                description="工具执行失败，可能是参数问题",
                actions=[
                    "检查工具参数格式",
                    "确认文件路径是否存在",
                    "确认参数类型正确",
                ],
                priority=Priority.HIGH,
            ),
            Suggestion(
                title="查看工具文档",
                description="查看工具使用说明",
                actions=[
                    "使用 /help 查看帮助",
                    "查看工具示例",
                ],
                priority=Priority.MEDIUM,
                command="/help",
            ),
        ],
        ErrorType.MODEL_ERROR: [
            Suggestion(
                title="检查 API Key",
                description="API Key 可能无效或已过期",
                actions=[
                    "检查 DEEPSEEK_API_KEY 环境变量",
                    "确认 API Key 是否有效",
                    "检查账户余额",
                ],
                priority=Priority.HIGH,
            ),
            Suggestion(
                title="切换模型",
                description="当前模型可能不可用",
                actions=[
                    "使用 /model 列出可用模型",
                    "切换到其他模型",
                ],
                priority=Priority.MEDIUM,
                command="/model",
            ),
        ],
        ErrorType.FILE_NOT_FOUND: [
            Suggestion(
                title="检查文件路径",
                description="指定的文件或目录不存在",
                actions=[
                    "确认文件路径拼写正确",
                    "使用绝对路径而非相对路径",
                    "检查当前工作目录",
                ],
                priority=Priority.HIGH,
            ),
            Suggestion(
                title="创建文件",
                description="如果需要创建新文件",
                actions=[
                    "使用 write_file 工具创建文件",
                    "检查父目录是否存在",
                ],
                priority=Priority.MEDIUM,
            ),
        ],
        ErrorType.INVALID_PARAMETER: [
            Suggestion(
                title="检查参数格式",
                description="参数格式或类型不正确",
                actions=[
                    "检查参数类型是否正确",
                    "确认必需参数是否提供",
                    "检查 JSON 格式是否有效",
                ],
                priority=Priority.HIGH,
            ),
        ],
        ErrorType.UNKNOWN: [
            Suggestion(
                title="重试操作",
                description="未知错误，尝试重新执行",
                actions=[
                    "重新描述任务",
                    "简化任务描述",
                    "检查错误日志",
                ],
                priority=Priority.LOW,
            ),
        ],
    }

    # Suggestions for each error type (English)
    SUGGESTIONS_EN: Dict[ErrorType, List[Suggestion]] = {
        ErrorType.API_RATE_LIMIT: [
            Suggestion(
                title="Wait and Retry",
                description="API rate limit exceeded, wait before retrying",
                actions=[
                    "Wait 60 seconds before retry",
                    "Check for duplicate requests",
                    "Reduce request frequency",
                ],
                priority=Priority.HIGH,
                command="/wait 60",
            ),
            Suggestion(
                title="Switch to Backup Model",
                description="Switch to a backup model to continue",
                actions=[
                    "Use /model command to switch",
                    "Recommended: deepseek-chat, gpt-4o-mini",
                ],
                priority=Priority.MEDIUM,
                command="/model",
            ),
        ],
        ErrorType.FILE_PERMISSION: [
            Suggestion(
                title="Check File Permissions",
                description="Current user may lack permissions",
                actions=[
                    "Check permissions: ls -la <path>",
                    "Modify permissions: chmod +x <path>",
                    "Check owner: stat <path>",
                ],
                priority=Priority.HIGH,
            ),
            Suggestion(
                title="Use Elevated Permissions",
                description="Run with administrator privileges",
                actions=[
                    "Windows: Run as Administrator",
                    "Linux/Mac: Use sudo",
                    "Check user groups: groups",
                ],
                priority=Priority.MEDIUM,
            ),
        ],
        ErrorType.NETWORK_TIMEOUT: [
            Suggestion(
                title="Check Network",
                description="Network connection may be unstable",
                actions=[
                    "Check network status",
                    "Try ping api.deepseek.com",
                    "Check proxy settings",
                ],
                priority=Priority.HIGH,
            ),
            Suggestion(
                title="Increase Timeout",
                description="Current timeout may be insufficient",
                actions=[
                    "Increase timeout in config",
                    "Set LLM_TIMEOUT=120",
                ],
                priority=Priority.MEDIUM,
            ),
        ],
        ErrorType.TOKEN_EXCEEDED: [
            Suggestion(
                title="Clear History",
                description="Conversation history too long",
                actions=[
                    "Use /clear to clean history",
                    "Start a new session",
                ],
                priority=Priority.HIGH,
                command="/clear",
            ),
            Suggestion(
                title="Switch to Large Context Model",
                description="Switch to a model with larger context",
                actions=[
                    "Recommended: claude-3-opus (200K)",
                    "Recommended: gpt-4-turbo (128K)",
                    "Use /model to switch",
                ],
                priority=Priority.MEDIUM,
                command="/model",
            ),
        ],
        ErrorType.TOOL_FAILURE: [
            Suggestion(
                title="Check Tool Parameters",
                description="Tool execution failed, check parameters",
                actions=[
                    "Check parameter format",
                    "Verify file path exists",
                    "Confirm parameter types",
                ],
                priority=Priority.HIGH,
            ),
            Suggestion(
                title="View Tool Docs",
                description="View tool documentation",
                actions=[
                    "Use /help for help",
                    "View tool examples",
                ],
                priority=Priority.MEDIUM,
                command="/help",
            ),
        ],
        ErrorType.MODEL_ERROR: [
            Suggestion(
                title="Check API Key",
                description="API Key may be invalid or expired",
                actions=[
                    "Check DEEPSEEK_API_KEY env var",
                    "Verify API Key is valid",
                    "Check account balance",
                ],
                priority=Priority.HIGH,
            ),
            Suggestion(
                title="Switch Model",
                description="Current model may be unavailable",
                actions=[
                    "Use /model to list models",
                    "Switch to another model",
                ],
                priority=Priority.MEDIUM,
                command="/model",
            ),
        ],
        ErrorType.FILE_NOT_FOUND: [
            Suggestion(
                title="Check File Path",
                description="Specified file or directory not found",
                actions=[
                    "Verify path spelling",
                    "Use absolute path",
                    "Check current directory",
                ],
                priority=Priority.HIGH,
            ),
            Suggestion(
                title="Create File",
                description="If creating a new file",
                actions=[
                    "Use write_file tool",
                    "Check parent directory exists",
                ],
                priority=Priority.MEDIUM,
            ),
        ],
        ErrorType.INVALID_PARAMETER: [
            Suggestion(
                title="Check Parameter Format",
                description="Parameter format or type incorrect",
                actions=[
                    "Check parameter types",
                    "Confirm required parameters",
                    "Validate JSON format",
                ],
                priority=Priority.HIGH,
            ),
        ],
        ErrorType.UNKNOWN: [
            Suggestion(
                title="Retry",
                description="Unknown error, try again",
                actions=[
                    "Restate the task",
                    "Simplify task description",
                    "Check error logs",
                ],
                priority=Priority.LOW,
            ),
        ],
    }

    def __init__(self, language: str = "zh"):
        """Initialize suggestion engine.

        Args:
            language: Language for suggestions ("zh" or "en")
        """
        self.language = language

    def analyze_error(self, error: str) -> Suggestion:
        """Analyze error and return the best suggestion.

        Args:
            error: Error message string

        Returns:
            Best matching Suggestion
        """
        error_type = self._classify_error(error)
        suggestions = self.get_suggestions(error_type)
        return suggestions[0] if suggestions else self._get_default_suggestion()

    def get_suggestions(self, error_type: ErrorType) -> List[Suggestion]:
        """Get all suggestions for an error type.

        Args:
            error_type: Type of error

        Returns:
            List of suggestions for the error type
        """
        suggestions_map = (
            self.SUGGESTIONS_CN if self.language == "zh" else self.SUGGESTIONS_EN
        )
        return suggestions_map.get(error_type, [self._get_default_suggestion()])

    def _classify_error(self, error: str) -> ErrorType:
        """Classify error message into ErrorType.

        Args:
            error: Error message string

        Returns:
            Classified ErrorType
        """
        error_lower = error.lower()

        # Check each pattern
        for pattern, error_type in self.ERROR_PATTERNS.items():
            if pattern in error_lower:
                return error_type

        return ErrorType.UNKNOWN

    def _get_default_suggestion(self) -> Suggestion:
        """Get default suggestion for unknown errors."""
        if self.language == "zh":
            return Suggestion(
                title="重试操作",
                description="遇到未知错误，请重试或联系支持",
                actions=[
                    "重新描述任务",
                    "检查错误日志",
                ],
                priority=Priority.LOW,
            )
        else:
            return Suggestion(
                title="Retry",
                description="Unknown error, please retry or contact support",
                actions=[
                    "Restate the task",
                    "Check error logs",
                ],
                priority=Priority.LOW,
            )

    def format_suggestion(self, suggestion: Suggestion) -> str:
        """Format suggestion for display.

        Args:
            suggestion: Suggestion to format

        Returns:
            Formatted string
        """
        lines = [
            f"[{suggestion.priority.value.upper()}] {suggestion.title}",
            f"  {suggestion.description}",
        ]
        if suggestion.actions:
            lines.append("  Actions:")
            for action in suggestion.actions:
                lines.append(f"    - {action}")
        if suggestion.command:
            lines.append(f"  Command: {suggestion.command}")
        return "\n".join(lines)


# Global instance
_suggestion_engine: Optional[SuggestionEngine] = None


def get_suggestion_engine(language: str = "zh") -> SuggestionEngine:
    """Get or create suggestion engine instance.

    Args:
        language: Language for suggestions ("zh" or "en")

    Returns:
        SuggestionEngine instance
    """
    global _suggestion_engine
    if _suggestion_engine is None or _suggestion_engine.language != language:
        _suggestion_engine = SuggestionEngine(language=language)
    return _suggestion_engine
