# Message 透传 API

这一页覆盖 `adapter.napcat.message.*` 下除强类型封装 API 外的透传 API。

统一调用方式：

```python
response = await self.ctx.api.call(
    "adapter.napcat.message.friend_poke",
    params={
        "group_id": 123456789,
        "user_id": 987654321,
        "target_id": 987654321,
    },
)
```

字段来源说明：

- `无参`：官方页面当前无请求字段。
- `Schema`：直接来自官方“请求参数”结构。

## API 列表

| API | 底层 action | 官方请求字段 | 来源 | 官方文档 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `adapter.napcat.message.ark_share_group` | `ArkShareGroup` | `group_id` | `Schema` | [官方](https://napcat.apifox.cn/226658971e0) | 分享群（Ark）。 |
| `adapter.napcat.message.ark_share_peer` | `ArkSharePeer` | `user_id`、`group_id`、`phone_number` | `Schema` | [官方](https://napcat.apifox.cn/226658965e0) | 分享用户（Ark）。 |
| `adapter.napcat.message.click_inline_keyboard_button` | `click_inline_keyboard_button` | `group_id`、`bot_appid`、`button_id`、`callback_data`、`msg_seq` | `Schema` | [官方](https://napcat.apifox.cn/266151864e0) | 点击内联键盘按钮。 |
| `adapter.napcat.message.fetch_emoji_like` | `fetch_emoji_like` | `message_id`、`emojiId`、`emojiType`、`count`、`cookie` | `Schema` | [官方](https://napcat.apifox.cn/226659219e0) | 获取表情点赞详情。 |
| `adapter.napcat.message.forward_friend_single_msg` | `forward_friend_single_msg` | `message_id`、`group_id`、`user_id` | `Schema` | [官方](https://napcat.apifox.cn/226659051e0) | 转发单条消息。 |
| `adapter.napcat.message.forward_group_single_msg` | `forward_group_single_msg` | `message_id`、`group_id`、`user_id` | `Schema` | [官方](https://napcat.apifox.cn/226659074e0) | 转发单条消息。 |
| `adapter.napcat.message.friend_poke` | `friend_poke` | `group_id`、`user_id`、`target_id` | `Schema` | [官方](https://napcat.apifox.cn/226659255e0) | 发送私聊戳一戳。 |
| `adapter.napcat.message.get_ai_record` | `get_ai_record` | `character`、`group_id`、`text` | `Schema` | [官方](https://napcat.apifox.cn/229486818e0) | 获取 AI 语音。 |
| `adapter.napcat.message.get_emoji_likes` | `get_emoji_likes` | `group_id`、`message_id`、`emoji_id`、`emoji_type`、`count` | `Schema` | [官方](https://napcat.apifox.cn/410334663e0) | 获取消息表情点赞列表。 |
| `adapter.napcat.message.get_friend_msg_history` | `get_friend_msg_history` | `user_id`、`message_seq`、`count`、`reverse_order`、`disable_get_url`、`parse_mult_msg`、`quick_reply`、`reverseOrder` | `Schema` | [官方](https://napcat.apifox.cn/226659174e0) | 官方页当前同时列出 `reverse_order` 和 `reverseOrder` 两种写法。 |
| `adapter.napcat.message.get_group_msg_history` | `get_group_msg_history` | `group_id`、`message_seq`、`count`、`reverse_order`、`disable_get_url`、`parse_mult_msg`、`quick_reply`、`reverseOrder` | `Schema` | [官方](https://napcat.apifox.cn/226657401e0) | 官方页当前同时列出 `reverse_order` 和 `reverseOrder` 两种写法。 |
| `adapter.napcat.message.mark_all_as_read` | `_mark_all_as_read` | 无 | `无参` | [官方](https://napcat.apifox.cn/226659194e0) | 标记所有消息已读。 |
| `adapter.napcat.message.mark_group_msg_as_read` | `mark_group_msg_as_read` | `user_id`、`group_id`、`message_id` | `Schema` | [官方](https://napcat.apifox.cn/226659167e0) | 标记群聊已读。 |
| `adapter.napcat.message.mark_msg_as_read` | `mark_msg_as_read` | `user_id`、`group_id`、`message_id` | `Schema` | [官方](https://napcat.apifox.cn/226657389e0) | 标记消息已读（Go-CQHTTP 兼容）。 |
| `adapter.napcat.message.mark_private_msg_as_read` | `mark_private_msg_as_read` | `user_id`、`group_id`、`message_id` | `Schema` | [官方](https://napcat.apifox.cn/226659165e0) | 标记私聊已读。 |
| `adapter.napcat.message.send_ark_share` | `send_ark_share` | `user_id`、`group_id`、`phone_number` | `Schema` | [官方](https://napcat.apifox.cn/410334665e0) | 分享用户（Ark）。 |
| `adapter.napcat.message.send_forward_msg` | `send_forward_msg` | `message_type`、`user_id`、`group_id`、`message`、`auto_escape`、`source`、`news`、`summary`、`prompt`、`timeout` | `Schema` | [官方](https://napcat.apifox.cn/226659136e0) | 官方页当前顶层请求字段就是这一组；真正的转发节点细节放在 `message` 内。 |
| `adapter.napcat.message.send_group_ark_share` | `send_group_ark_share` | `group_id` | `Schema` | [官方](https://napcat.apifox.cn/410334664e0) | 分享群（Ark）。 |
| `adapter.napcat.message.send_group_forward_msg` | `send_group_forward_msg` | `message_type`、`user_id`、`group_id`、`message`、`auto_escape`、`source`、`news`、`summary`、`prompt`、`timeout` | `Schema` | [官方](https://napcat.apifox.cn/226657396e0) | 发送群合并转发消息。 |
| `adapter.napcat.message.send_msg` | `send_msg` | `message_type`、`user_id`、`group_id`、`message`、`auto_escape`、`source`、`news`、`summary`、`prompt`、`timeout` | `Schema` | [官方](https://napcat.apifox.cn/226656652e0) | 通用发送消息。 |
| `adapter.napcat.message.send_private_forward_msg` | `send_private_forward_msg` | `message_type`、`user_id`、`group_id`、`message`、`auto_escape`、`source`、`news`、`summary`、`prompt`、`timeout` | `Schema` | [官方](https://napcat.apifox.cn/226657399e0) | 发送私聊合并转发消息。 |
| `adapter.napcat.message.send_private_msg` | `send_private_msg` | `message_type`、`user_id`、`group_id`、`message`、`auto_escape`、`source`、`news`、`summary`、`prompt`、`timeout` | `Schema` | [官方](https://napcat.apifox.cn/226656553e0) | 发送私聊消息。 |

## 典型示例

```python
response = await self.ctx.api.call(
    "adapter.napcat.message.send_msg",
    params={
        "message_type": "group",
        "group_id": 123456789,
        "message": [{"type": "text", "data": {"text": "你好，MaiBot"}}],
    },
)
```
