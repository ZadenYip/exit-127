class LoginIdAlreadyExistsError(Exception):
    """登录 ID 已经存在。"""


class UserNotFoundError(Exception):
    """用户不存在。"""


class SessionIdCollisionError(Exception):
    """会话 ID 冲突。"""
