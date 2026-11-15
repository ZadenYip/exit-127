# 班级 API 对接说明

面向前后端联调，描述当前接口的调用方式、响应和页面交互。

## 通用约定

- 所有接口需要登录，浏览器携带登录接口设置的 `__Host-session_id` Cookie，不使用 Bearer Token。
- Cookie 为 HttpOnly、Secure、SameSite=Strict。联调使用 HTTPS；跨源调用还需要部署侧允许携带凭据的 CORS 配置，`credentials: "include"` 不会绕过 SameSite 限制。
- 当前用户身份从会话获取，请求中不传 `teacher_id`、`student_id` 或 `role`。
- 有请求体时使用 `Content-Type: application/json`，不接受未声明字段。
- 路径中的 `class_id` 是大于 0 的整数。
- 成功响应直接返回对象、数组或布尔值，没有 `data` 包装。
- `204` 无响应体，前端不要调用 `response.json()`。

## 接口总览

| 方法 | 路径 | 调用身份 | 成功响应 |
| --- | --- | --- | --- |
| POST | `/v1/classes` | 老师 | 201，班级对象 |
| GET | `/v1/classes` | 老师或学生 | 200，班级数组 |
| GET | `/v1/classes/{class_id}` | 所属老师或班级成员 | 200，班级详情 |
| DELETE | `/v1/classes/{class_id}` | 所属老师 | 204 |
| POST | `/v1/classes/{class_id}:createJoinLink` | 所属老师 | 201，邀请码对象 |
| POST | `/v1/classes/{class_id}:revokeJoinLink` | 所属老师 | 204 |
| POST | `/v1/classes:join` | 学生 | 200，true 或 false |
| POST | `/v1/classes/{class_id}:leave` | 班级学生成员 | 204 |

冒号动作是路径的一部分，例如 `/v1/classes/10000:createJoinLink`。

## 班级响应结构

创建和列表中的班级对象只有以下四个字段：

```json
{
  "id": 10000,
  "name": "高一（3）班",
  "description": "英语学习班",
  "teacher_id": 10001
}
```

| 字段 | JSON 类型 | 含义 |
| --- | --- | --- |
| id | number（整数） | 班级 ID |
| name | string | 班级名称 |
| description | string 或 null | 班级简介 |
| teacher_id | number（整数） | 所属老师 ID |

详情额外返回 `member_count`（整数，学生成员数）。不返回老师姓名、成员名单或创建时间。

## 1. 创建班级

`POST /v1/classes`

```json
{
  "name": "高一（3）班",
  "description": "英语学习班"
}
```

| 字段 | 必填 | 规则 |
| --- | --- | --- |
| name | 是 | 输入长度 1–16 字符；去除首尾空白后不能是空串 |
| description | 否 | 最多 128 字符；省略或 null 表示无简介，允许空字符串 |

名称长度校验先于去除首尾空白，前端宜先 trim 再提交。

成功返回 `201` 和班级对象。前端可将其加入列表或进入详情页。

## 2. 获取我的班级

`GET /v1/classes`

无请求体、无分页或筛选参数。成功返回 `200` 和班级对象数组，没有班级时返回 `[]`。

- 老师获得自己创建的有效班级。
- 学生获得自己加入的有效班级。
- 已删除班级不会出现在列表中。
- 管理员等其他角色返回 `403 FORBIDDEN`。

## 3. 获取班级详情

`GET /v1/classes/{class_id}`

无请求体。成功返回 `200`：

```json
{
  "id": 10000,
  "name": "高一（3）班",
  "description": "英语学习班",
  "teacher_id": 10001,
  "member_count": 12
}
```

不存在、已删除或无权查看，统一返回 `404 CLASS_NOT_FOUND`。前端按“班级不存在或不可访问”处理，不据此判断班级是否真实存在。

## 4. 删除班级

`DELETE /v1/classes/{class_id}`

无请求体。成功返回 `204`，前端从列表移除班级并退出该班级详情页。

删除后班级不能再查看或加入，原邀请失效；当前没有恢复接口。不存在、已删除或不属于当前老师的班级返回 `404 CLASS_NOT_FOUND`，重复删除也返回此错误。

## 5. 创建或重置加入邀请

`POST /v1/classes/{class_id}:createJoinLink`

需要 JSON 请求体。设置暗号时：

```json
{"passphrase": "一起学习"}
```

无需暗号时发送 `{}` 或 `{"passphrase": null}`，不要省略整个请求体。

暗号非 null 时长度为 1–16 字符，不允许空字符串，按原值比较，不自动去除空白。

成功返回 `201`：

```json
{"invite_code": "01912345-6789-7abc-8def-0123456789ab"}
```

- 将邀请码当作不透明字符串传递，无需在前端解析 UUID 版本。
- 每个班级只有一个当前邀请。再次调用会重置邀请，旧邀请码立即失效。
- 每次创建或重置后有效期为 7 天，到期即不可使用。
- 重置时省略暗号表示新邀请无需暗号，不沿用旧暗号。
- 响应只返回邀请码，不返回完整 URL、班级 ID、暗号或到期时间。
- 班级不存在、已删除或不属于当前老师时返回 `404 CLASS_NOT_FOUND`。

## 6. 撤销加入邀请

`POST /v1/classes/{class_id}:revokeJoinLink`

无请求体。成功返回 `204`，原邀请码不可再使用，不影响已加入的学生。

| 情况 | 响应 |
| --- | --- |
| 班级不存在、已删除或不属于当前老师 | 404 CLASS_NOT_FOUND，班级不存在 |
| 班级有效但没有邀请，包括从未创建或已经撤销 | 404 INVITE_NOT_FOUND，邀请已不存在 |

重复撤销返回 404，不是 204。前端收到“邀请已不存在”后可清除本地展示的邀请。

## 7. 学生加入班级

`POST /v1/classes:join`

```json
{
  "invite_code": "01912345-6789-7abc-8def-0123456789ab",
  "passphrase": "一起学习"
}
```

| 字段 | 必填 | 规则 |
| --- | --- | --- |
| invite_code | 是 | 1–64 字符；提交邀请码，不提交整条 URL |
| passphrase | 否 | 省略或 null 表示不提供暗号；提供时长度为 1–16 字符 |

成功返回 `200`，响应体是 JSON 布尔值：

- `true`：本次成功加入。
- `false`：已经是成员，无需再次加入，不是请求失败。

两种结果均可刷新“我的班级”列表。加入响应不带班级 ID，不能从邀请码推导详情页地址。

| 情况 | 响应及处理 |
| --- | --- |
| 邀请要求暗号，但未提供或不匹配 | 400 INVITE_PASSPHRASE_MISMATCH，提示输入或修正暗号 |
| 邀请无效、已重置、撤销、到期，或班级已删除 | 404 INVITE_NOT_FOUND，提示重新获取链接 |
| 非学生调用 | 403 FORBIDDEN |

即使已经是成员，也需要先通过邀请有效性和暗号检查，才能返回 false。

### 分享链接交互流程

分享 URL 指向前端加入页面，例如：

```text
https://<前端域名>/join-class?invite_code=<邀请码>
```

这是前端路由示例，不是后端 API，页面路径可自行定义。

1. 老师创建邀请，前端用返回的邀请码生成分享 URL，通过 `URLSearchParams` 编码参数。
2. 学生打开页面，从 URL 读取邀请码；未登录则先登录，并保留邀请码以便返回页面。
3. 学生确认加入，前端调用 `POST /v1/classes:join`，将邀请码和可选暗号放入 JSON 请求体。
4. 暗号不匹配时展示输入框并允许重试；成功后刷新班级列表。

打开链接本身不会加入班级。后端当前没有 GET 加入接口，也没有凭邀请码预览班级、查询是否需要暗号或获取现有邀请的接口。

## 8. 学生退出班级

`POST /v1/classes/{class_id}:leave`

无请求体，仅退出当前登录学生自己的成员关系。

- 成功返回 `204`，前端移除列表中的该班级。
- 班级不存在或已删除：`404 CLASS_NOT_FOUND`。
- 当前学生不是成员，包括已退出后再次退出：`403 FORBIDDEN`，消息为“你不是该班级成员”。
- 非学生调用：`403 FORBIDDEN`。

## 错误响应与处理

业务及鉴权错误示例：

```json
{
  "detail": {
    "code": "CLASS_NOT_FOUND",
    "message": "班级不存在"
  }
}
```

| HTTP 状态 | code | 前端处理 |
| --- | --- | --- |
| 401 | UNAUTHENTICATED | 提示登录或重新登录；加入流程保留邀请码 |
| 403 | FORBIDDEN | 提示无权限或非班级成员，不当作登录失效 |
| 404 | CLASS_NOT_FOUND | 提示班级不可访问，按场景刷新列表或返回列表页 |
| 404 | INVITE_NOT_FOUND | 加入时提示“加入链接无效或已过期”；撤销时提示“邀请已不存在” |
| 400 | INVITE_PASSPHRASE_MISMATCH | 提示“暗号不匹配”并允许重试 |

前端依据 HTTP 状态、`detail.code` 和当前操作处理，不通过匹配中文消息决定业务分支。

参数校验失败返回 `422`，其 `detail` 是数组，与上述错误对象不同。数组元素包含 `loc`、`msg`、`type` 等信息：

- `loc: ["body", "name"]`：请求体中的名称有误。
- `loc: ["path", "class_id"]`：路径中的班级 ID 有误。

空字符串暗号、超长字段、缺少必填字段、额外请求字段等都属于 422。前端按 loc 定位字段，并兼容额外错误信息。网络失败或 5xx 使用通用失败提示，不假定响应一定包含业务错误码。

