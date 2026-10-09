# 强类型封装 API

这一页只写“强类型封装 API”。

调用规则：

- 直接使用 `self.ctx.api.call("完整 API 名", **kwargs)`。
- 不要把参数再包进 `params`。
- 如果 `response["success"]` 为真，真正的业务结果在 `response["result"]`。

## 通用入口

| API | 适配器直接参数 | 官方 action | 官方请求字段 | 官方文档 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `adapter.napcat.action.call` | `action_name`、`params=None` | 任意 action | 由 `action_name` 决定 | 无 | 适配器通用入口；`result` 为 NapCat 原始响应字典。 |
| `adapter.napcat.action.call_data` | `action_name`、`params=None` | 任意 action | 由 `action_name` 决定 | 无 | 适配器通用入口；`result` 直接返回 NapCat 响应里的 `data`。 |

## System

| API | 适配器直接参数 | 官方 action | 官方请求字段 | 官方文档 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `adapter.napcat.system.get_login_info` | 无 | `get_login_info` | 无 | [官方](https://napcat.apifox.cn/226656952e0) | `result` 为 `dict \| None`；失败返回 `None`。 |

## Account

| API | 适配器直接参数 | 官方 action | 官方请求字段 | 官方文档 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `adapter.napcat.account.set_qq_profile` | `nickname`、`personal_note=""`、`sex=""` | `set_qq_profile` | `nickname`、`personal_note`、`sex` | [官方](https://napcat.apifox.cn/226657374e0) | `nickname` 必填；`sex` 仅允许 `male` / `female` / `unknown`；空 `personal_note` 和空 `sex` 不会下发。 |
| `adapter.napcat.account.get_stranger_info` | `user_id`、`no_cache=False` | `get_stranger_info` | `user_id`、`no_cache` | [官方](https://napcat.apifox.cn/226656970e0) | 适配器已对齐官方隐藏 schema；官方默认示例只展示 `user_id`，但页面内嵌 schema 还定义了 `no_cache`；`result` 为 `dict \| None`。 |
| `adapter.napcat.account.get_friend_list` | `no_cache=False` | `get_friend_list` | `no_cache` | [官方](https://napcat.apifox.cn/226656976e0) | `result` 为归一化后的好友列表；NapCat 不同版本下若把列表包在 `friend_list` / `data` 里，适配器会自动展开。 |

## Group

| API | 适配器直接参数 | 官方 action | 官方请求字段 | 官方文档 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `adapter.napcat.group.set_group_ban` | `group_id`、`user_id`、`duration` | `set_group_ban` | `group_id`、`user_id`、`duration` | [官方](https://napcat.apifox.cn/226656791e0) | `duration` 必须是 `0` 到 `2592000` 之间的非负整数。 |
| `adapter.napcat.group.set_group_whole_ban` | `group_id`、`enable` | `set_group_whole_ban` | `group_id`、`enable` | [官方](https://napcat.apifox.cn/226656802e0) | `enable` 会被规范成布尔值。 |
| `adapter.napcat.group.set_group_kick` | `group_id`、`user_id`、`reject_add_request=False` | `set_group_kick` | `group_id`、`user_id`、`reject_add_request` | [官方](https://napcat.apifox.cn/226656748e0) | 单个踢人封装。 |
| `adapter.napcat.group.set_group_kick_members` | `group_id`、`user_id`、`reject_add_request=False` | `set_group_kick_members` | `group_id`、`user_id`、`reject_add_request` | [官方](https://napcat.apifox.cn/301542209e0) | 适配器要求 `user_id` 传数组，并实际下发 `user_id: [ ... ]`。 |
| `adapter.napcat.group.set_group_name` | `group_id`、`group_name` | `set_group_name` | `group_id`、`group_name` | [官方](https://napcat.apifox.cn/226656919e0) | `group_name` 会被规范成非空字符串。 |
| `adapter.napcat.group.get_group_info` | `group_id` | `get_group_info` | `group_id` | [官方](https://napcat.apifox.cn/226656979e0) | `result` 为 `dict \| None`。 |
| `adapter.napcat.group.get_group_detail_info` | `group_id` | `get_group_detail_info` | `group_id` | [官方](https://napcat.apifox.cn/307180859e0) | `result` 为 `dict \| None`。 |
| `adapter.napcat.group.get_group_list` | `no_cache=False` | `get_group_list` | `no_cache` | [官方](https://napcat.apifox.cn/226656992e0) | `result` 为归一化后的群列表。 |
| `adapter.napcat.group.get_group_at_all_remain` | `group_id` | `get_group_at_all_remain` | `group_id` | [官方](https://napcat.apifox.cn/227245941e0) | `result` 为 `dict \| None`；不同 NapCat 版本下返回字段名可能不同。 |
| `adapter.napcat.group.get_group_member_info` | `group_id`、`user_id`、`no_cache=True` | `get_group_member_info` | `group_id`、`user_id`、`no_cache` | [官方](https://napcat.apifox.cn/226657019e0) | `group_id` / `user_id` 会先规范化为正整数，再转字符串下发。 |
| `adapter.napcat.group.get_group_member_list` | `group_id`、`no_cache=False` | `get_group_member_list` | `group_id`、`no_cache` | [官方](https://napcat.apifox.cn/226657034e0) | `result` 为归一化后的成员列表。 |

## Message

| API | 适配器直接参数 | 官方 action | 官方请求字段 | 官方文档 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `adapter.napcat.message.send_poke` | `user_id=None`、`group_id=None`、`target_id=None`、`qq_id=None` | `send_poke` | `group_id`、`user_id`、`target_id` | [官方](https://napcat.apifox.cn/250286923e0) | 优先使用官方字段 `user_id` / `group_id` / `target_id`；`qq_id` 仅作为旧版兼容别名，会映射成 `user_id`。 |
| `adapter.napcat.message.delete_msg` | `message_id` | `delete_msg` | `message_id` | [官方](https://napcat.apifox.cn/226919954e0) | `message_id` 必须是正整数。 |
| `adapter.napcat.message.send_group_ai_record` | `group_id`、`character`、`text` | `send_group_ai_record` | `character`、`group_id`、`text` | [官方](https://napcat.apifox.cn/229486774e0) | `character` 和 `text` 都会被规范成非空字符串。 |
| `adapter.napcat.message.set_msg_emoji_like` | `message_id`、`emoji_id`、`set=True` | `set_msg_emoji_like` | `message_id`、`emoji_id`、`set` | [官方](https://napcat.apifox.cn/226659104e0) | 适配器把 `set` 下发为官方字段 `set`。 |
| `adapter.napcat.message.get_msg` | `message_id` | `get_msg` | `message_id` | [官方](https://napcat.apifox.cn/226656707e0) | `result` 为 `dict \| None`。 |
| `adapter.napcat.message.get_forward_msg` | `message_id=""`、`id=""` | `get_forward_msg` | `message_id`、`id` | [官方](https://napcat.apifox.cn/226656712e0) | 适配器已对齐官方隐藏 schema；至少提供一个字段；若两个字段同时传入则要求值一致；`result` 会统一整理成 `{\"messages\": [...]}`。 |

## File

| API | 适配器直接参数 | 官方 action | 官方请求字段 | 官方文档 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `adapter.napcat.file.get_record` | `file=""`、`file_id=""`、`out_format="wav"` | `get_record` | `file`、`file_id`、`out_format` | [官方](https://napcat.apifox.cn/226657058e0) | 适配器已对齐官方隐藏 schema；`file` / `file_id` 至少提供一个；`out_format` 默认仍为 `wav`，以兼容旧行为。 |

## 典型示例

```python
response = await self.ctx.api.call(
    "adapter.napcat.message.send_poke",
    user_id=987654321,
    group_id=123456789,
    target_id=123456789,
)
```

```python
response = await self.ctx.api.call(
    "adapter.napcat.group.get_group_member_info",
    group_id=123456789,
    user_id=987654321,
    no_cache=True,
)
```
