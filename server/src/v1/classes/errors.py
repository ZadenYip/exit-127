class ClassNotFoundError(Exception):
    """班级不存在、已删除或当前用户无权访问。"""


class ClassAccessDeniedError(Exception):
    """当前用户角色不能执行班级操作。"""


class InviteNotFoundError(Exception):
    """邀请不存在、已撤销、已过期或对应班级已删除。"""


class InvitePassphraseMismatchError(Exception):
    """加入班级时提供的暗号不匹配。"""


class ClassMembershipRequiredError(Exception):
    """当前学生不是该班级成员。"""
