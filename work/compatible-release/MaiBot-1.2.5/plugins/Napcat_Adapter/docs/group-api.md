# Group 透传 API

这一页覆盖 `adapter.napcat.group.*` 下除强类型封装 API 外的透传 API。

统一调用方式：

```python
response = await self.ctx.api.call(
    "adapter.napcat.group.set_group_admin",
    params={
        "group_id": 123456789,
        "user_id": 987654321,
        "enable": True,
    },
)
```

字段来源说明：

- `无参`：官方页面当前无请求字段。
- `Schema`：直接来自官方“请求参数”结构。
- `示例`：官方页面 Schema 未展开字段，参数来自同页 `curl --data-raw` 示例。

## API 列表

| API | 底层 action | 官方请求字段 | 来源 | 官方文档 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `adapter.napcat.group.delete_essence_msg` | `delete_essence_msg` | `message_id`、`msg_seq`、`msg_random`、`group_id` | `Schema` | [官方](https://napcat.apifox.cn/226658678e0) | 官方页当前除了 `message_id` 还列出兼容字段；适配器这里完全透传。 |
| `adapter.napcat.group.delete_group_notice` | `_del_group_notice` | `group_id`、`notice_id` | `Schema` | [官方](https://napcat.apifox.cn/226659240e0) | 删除群公告。 |
| `adapter.napcat.group.get_essence_msg_list` | `get_essence_msg_list` | `group_id` | `Schema` | [官方](https://napcat.apifox.cn/226658664e0) | 获取群精华消息。 |
| `adapter.napcat.group.get_group_honor_info` | `get_group_honor_info` | `group_id`、`type` | `Schema` | [官方](https://napcat.apifox.cn/226657036e0) | 获取群荣誉信息。 |
| `adapter.napcat.group.get_group_ignore_add_request` | `get_group_ignore_add_request` | 无 | `无参` | [官方](https://napcat.apifox.cn/226659234e0) | 获取群被忽略的加群请求。 |
| `adapter.napcat.group.get_group_ignored_notifies` | `get_group_ignored_notifies` | 无 | `无参` | [官方](https://napcat.apifox.cn/226659323e0) | 获取群忽略通知。 |
| `adapter.napcat.group.get_group_info_ex` | `get_group_info_ex` | `group_id` | `Schema` | [官方](https://napcat.apifox.cn/226659229e0) | 获取群详细信息（扩展）。 |
| `adapter.napcat.group.get_group_notice` | `_get_group_notice` | `group_id` | `Schema` | [官方](https://napcat.apifox.cn/226658742e0) | 获取群公告。 |
| `adapter.napcat.group.get_group_shut_list` | `get_group_shut_list` | `group_id` | `Schema` | [官方](https://napcat.apifox.cn/226659300e0) | 获取群禁言列表。 |
| `adapter.napcat.group.get_group_system_msg` | `get_group_system_msg` | `count` | `Schema` | [官方](https://napcat.apifox.cn/226658660e0) | 获取群系统消息。 |
| `adapter.napcat.group.get_guild_list` | `get_guild_list` | 无 | `无参` | [官方](https://napcat.apifox.cn/226659311e0) | 获取频道列表。 |
| `adapter.napcat.group.get_guild_service_profile` | `get_guild_service_profile` | `guild_id` | `示例` | [官方](https://napcat.apifox.cn/226659317e0) | 官方页左侧 Schema 当前只显示 `object`，同页示例请求体给出 `guild_id`。 |
| `adapter.napcat.group.group_poke` | `group_poke` | `group_id`、`user_id`、`target_id` | `Schema` | [官方](https://napcat.apifox.cn/226659265e0) | 发送群聊戳一戳。 |
| `adapter.napcat.group.handle_quick_operation_internal` | `.handle_quick_operation` | `context`、`operation` | `Schema` | [官方](https://napcat.apifox.cn/226658889e0) | 处理快速操作。 |
| `adapter.napcat.group.send_group_msg` | `send_group_msg` | `message_type`、`user_id`、`group_id`、`message`、`auto_escape`、`source`、`news`、`summary`、`prompt`、`timeout` | `Schema` | [官方](https://napcat.apifox.cn/226656598e0) | 官方页当前顶层请求字段就是这一组；真正的消息段细节放在 `message` 内。 |
| `adapter.napcat.group.send_group_notice` | `_send_group_notice` | `group_id`、`content`、`image`、`pinned`、`type`、`confirm_required`、`is_show_edit_card`、`tip_window_type` | `Schema` | [官方](https://napcat.apifox.cn/226658740e0) | 发送群公告。 |
| `adapter.napcat.group.send_group_sign` | `send_group_sign` | `group_id` | `Schema` | [官方](https://napcat.apifox.cn/230897177e0) | NapCat 另外提供的“群打卡”动作。 |
| `adapter.napcat.group.set_essence_msg` | `set_essence_msg` | `message_id` | `Schema` | [官方](https://napcat.apifox.cn/226658674e0) | 设置精华消息。 |
| `adapter.napcat.group.set_group_add_option` | `set_group_add_option` | `group_id`、`add_type`、`group_question`、`group_answer` | `Schema` | [官方](https://napcat.apifox.cn/301542178e0) | 设置群加群选项。 |
| `adapter.napcat.group.set_group_add_request` | `set_group_add_request` | `flag`、`approve`、`reason`、`count` | `Schema` | [官方](https://napcat.apifox.cn/226656947e0) | 官方页当前字段与旧版常见的 `sub_type` 方案不同；文档按当前官方页记录。 |
| `adapter.napcat.group.set_group_admin` | `set_group_admin` | `group_id`、`user_id`、`enable` | `Schema` | [官方](https://napcat.apifox.cn/226656815e0) | 设置群管理员。 |
| `adapter.napcat.group.set_group_card` | `set_group_card` | `group_id`、`user_id`、`card` | `Schema` | [官方](https://napcat.apifox.cn/226656913e0) | 设置群名片。 |
| `adapter.napcat.group.set_group_leave` | `set_group_leave` | `group_id`、`is_dismiss` | `Schema` | [官方](https://napcat.apifox.cn/226656926e0) | 退出群组。 |
| `adapter.napcat.group.set_group_portrait` | `set_group_portrait` | `file`、`group_id` | `Schema` | [官方](https://napcat.apifox.cn/226658669e0) | 设置群头像。 |
| `adapter.napcat.group.set_group_remark` | `set_group_remark` | `group_id`、`remark` | `Schema` | [官方](https://napcat.apifox.cn/283136268e0) | 设置群备注。 |
| `adapter.napcat.group.set_group_robot_add_option` | `set_group_robot_add_option` | `group_id`、`robot_member_switch`、`robot_member_examine` | `Schema` | [官方](https://napcat.apifox.cn/301542198e0) | 设置群机器人加群选项。 |
| `adapter.napcat.group.set_group_search` | `set_group_search` | `group_id`、`no_code_finger_open`、`no_finger_open` | `Schema` | [官方](https://napcat.apifox.cn/301542170e0) | 设置群搜索选项。 |
| `adapter.napcat.group.set_group_sign` | `set_group_sign` | `group_id` | `Schema` | [官方](https://napcat.apifox.cn/226659329e0) | 群打卡。 |
| `adapter.napcat.group.set_group_special_title` | `set_group_special_title` | `group_id`、`user_id`、`special_title` | `Schema` | [官方](https://napcat.apifox.cn/226656931e0) | 设置专属头衔。 |
| `adapter.napcat.group.set_group_todo` | `set_group_todo` | `group_id`、`message_id`、`message_seq` | `Schema` | [官方](https://napcat.apifox.cn/395460568e0) | 设置群待办。 |

## 典型示例

```python
response = await self.ctx.api.call(
    "adapter.napcat.group.send_group_msg",
    params={
        "message_type": "group",
        "group_id": 123456789,
        "message": [{"type": "text", "data": {"text": "你好"}}],
    },
)
```
