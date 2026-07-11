"""鉴权系统 v1.0：bcrypt + JWT（access/refresh）+ psycopg 用户存储 + 依赖。

路由侧统一 `from webui_new.auth import require_path_user` 即可注入
「鉴权 + 身份一致性」合一依赖（design.md §3.1 / §3.4 / §5）。
"""
from webui_new.auth.deps import get_current_user, require_admin, require_path_user
from webui_new.auth.storage import User

__all__ = ["User", "get_current_user", "require_admin", "require_path_user"]
