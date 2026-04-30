"""Completion condition configuration - 任务完成条件配置."""

from typing import Dict, List, Callable, Optional
from dataclasses import dataclass
import os


@dataclass
class CompletionCondition:
    """任务完成条件配置"""
    name: str                               # 模板名称
    required_files: List[str]               # 必需文件
    optional_files: Optional[List[str]] = None  # 可选文件
    custom_check: Optional[Callable] = None     # 自定义检查函数


# 预定义的项目模板
PROJECT_TEMPLATES: Dict[str, CompletionCondition] = {
    "web_basic": CompletionCondition(
        name="基础 Web 项目",
        required_files=["index.html", "style.css", "script.js"],
        optional_files=["css/style.css", "js/main.js", "js/script.js"],
    ),
    "web_react": CompletionCondition(
        name="React 项目",
        required_files=["src/App.jsx", "src/index.jsx", "package.json"],
        optional_files=["public/index.html", "src/App.tsx", "src/index.tsx"],
    ),
    "backend_fastapi": CompletionCondition(
        name="FastAPI 项目",
        required_files=["main.py", "requirements.txt"],
        optional_files=["models.py", "routes.py", "app.py"],
    ),
    "backend_flask": CompletionCondition(
        name="Flask 项目",
        required_files=["app.py", "requirements.txt"],
        optional_files=["main.py", "routes.py"],
    ),
}


def detect_project_type(task: str) -> Optional[str]:
    """从任务描述检测项目类型

    Args:
        task: 任务描述

    Returns:
        项目类型键名，或 None（无法识别）
    """
    task_lower = task.lower()

    # React 项目
    if any(kw in task_lower for kw in ["react", "jsx", "tsx", "component", "react项目"]):
        return "web_react"

    # FastAPI 项目
    if any(kw in task_lower for kw in ["fastapi", "fastapi项目", "python api", "python后端"]):
        return "backend_fastapi"

    # Flask 项目
    if any(kw in task_lower for kw in ["flask", "flask项目"]):
        return "backend_flask"

    # 基础 Web 项目
    if any(kw in task_lower for kw in ["web", "网站", "网页", "html", "前端项目", "静态网站"]):
        return "web_basic"

    return None


def check_project_completion(
    workspace: str,
    project_type: str
) -> Dict[str, any]:
    """检查项目文件是否完整

    Args:
        workspace: 工作目录路径
        project_type: 项目类型键名

    Returns:
        检查结果字典：
        - complete: bool - 是否完成
        - missing: List[str] - 缺失文件
        - existing: List[str] - 已存在文件
    """
    template = PROJECT_TEMPLATES.get(project_type)
    if not template:
        # 未知类型，默认完成（交给 LLM 判断）
        return {"complete": True, "missing": [], "existing": []}

    result = {
        "complete": True,
        "missing": [],
        "existing": [],
        "project_name": template.name,
    }

    # 检查必需文件
    for file in template.required_files:
        path = os.path.join(workspace, file)
        if os.path.exists(path):
            result["existing"].append(file)
        else:
            result["missing"].append(file)
            result["complete"] = False

    # 检查可选文件（只记录，不影响完成判断）
    if template.optional_files:
        for file in template.optional_files:
            path = os.path.join(workspace, file)
            if os.path.exists(path):
                result["existing"].append(file)

    return result


def check_web_project_completion(workspace: str) -> Dict[str, any]:
    """检查 Web 项目（HTML/CSS/JS）是否完整

    保留原有检查逻辑，用于快速判断。

    Args:
        workspace: 工作目录路径

    Returns:
        检查结果
    """
    html_path = os.path.join(workspace, "index.html")
    css_exists = os.path.exists(os.path.join(workspace, "style.css")) or \
                 os.path.exists(os.path.join(workspace, "css", "style.css"))
    js_exists = os.path.exists(os.path.join(workspace, "script.js")) or \
                os.path.exists(os.path.join(workspace, "js", "main.js")) or \
                os.path.exists(os.path.join(workspace, "js", "script.js"))

    has_html = os.path.exists(html_path)
    has_css = css_exists
    has_js = js_exists

    missing = []
    if not has_html:
        missing.append("index.html")
    if not has_css:
        missing.append("style.css")
    if not has_js:
        missing.append("script.js")

    return {
        "complete": has_html and has_css and has_js,
        "missing": missing,
        "existing": [f for f in ["index.html", "style.css", "script.js"] if f not in missing],
        "has_html": has_html,
        "has_css": has_css,
        "has_js": has_js,
    }


def check_backend_project_completion(workspace: str) -> Dict[str, any]:
    """检查后端项目（Python）是否完整

    Args:
        workspace: 工作目录路径

    Returns:
        检查结果
    """
    main_py = os.path.join(workspace, "main.py")
    app_py = os.path.join(workspace, "app.py")
    requirements = os.path.join(workspace, "requirements.txt")

    has_main = os.path.exists(main_py)
    has_app = os.path.exists(app_py)
    has_requirements = os.path.exists(requirements)

    # 至少有一个入口文件 + requirements.txt
    has_entry = has_main or has_app

    missing = []
    if not has_entry:
        missing.append("main.py 或 app.py")
    if not has_requirements:
        missing.append("requirements.txt")

    return {
        "complete": has_entry and has_requirements,
        "missing": missing,
        "existing": [],
        "has_main": has_main,
        "has_app": has_app,
        "has_requirements": has_requirements,
    }