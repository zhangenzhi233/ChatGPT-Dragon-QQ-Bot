# Account 透传 API

这一页覆盖 `adapter.napcat.account.*` 下除强类型封装 API 外的透传 API。

统一调用方式：

```python
response = await self.ctx.api.call(
    "adapter.napcat.account.send_like",
    params={
        "user_id": 123456789,
        "times": 10,
    },
)
```

字段来源说明：

- `无参`：官方页面当前无请求字段。
- `Schema`：直接来自官方“请求参数”结构。
- `示例`：官方页面 Schema 没展开出具体字段，参数来自同页 `curl --data-raw` 示例。

## API 列表

| API | 底层 action | 官方请求字段 | 来源 | 官方文档 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `adapter.napcat.account.create_collection` | `create_collection` | `rawData`、`brief` | `Schema` | [官方](https://napcat.apifox.cn/226659178e0) | 创建收藏。 |
| `adapter.napcat.account.delete_friend` | `delete_friend` | `friend_id`、`user_id`、`temp_block`、`temp_both_del` | `Schema` | [官方](https://napcat.apifox.cn/227237873e0) | 删除好友。 |
| `adapter.napcat.account.fetch_custom_face` | `fetch_custom_face` | `count` | `Schema` | [官方](https://napcat.apifox.cn/226659210e0) | 获取自定义表情。 |
| `adapter.napcat.account.get_ai_characters` | `get_ai_characters` | `group_id`、`chat_type` | `Schema` | [官方](https://napcat.apifox.cn/229485683e0) | 获取 AI 角色列表。 |
| `adapter.napcat.account.get_clientkey` | `get_clientkey` | 无 | `无参` | [官方](https://napcat.apifox.cn/250286915e0) | 获取 ClientKey。 |
| `adapter.napcat.account.get_collection_list` | `get_collection_list` | `category`、`count` | `Schema` | [官方](https://napcat.apifox.cn/226659182e0) | 获取收藏列表。 |
| `adapter.napcat.account.get_cookies` | `get_cookies` | `domain` | `Schema` | [官方](https://napcat.apifox.cn/226657041e0) | 获取 Cookies。 |
| `adapter.napcat.account.get_friends_with_category` | `get_friends_with_category` | 无 | `无参` | [官方](https://napcat.apifox.cn/226658978e0) | 获取带分组的好友列表。 |
| `adapter.napcat.account.get_mini_app_ark` | `get_mini_app_ark` | `type`、`title`、`desc`、`picUrl`、`jumpUrl` | `示例` | [官方](https://napcat.apifox.cn/227738594e0) | 官方页当前为 `Any Of` 结构，但左侧 Schema 未展开具体顶层字段，这里按同页示例请求体记录。 |
| `adapter.napcat.account.get_profile_like` | `get_profile_like` | `user_id`、`start`、`count` | `Schema` | [官方](https://napcat.apifox.cn/226659197e0) | 获取资料点赞。 |
| `adapter.napcat.account.get_recent_contact` | `get_recent_contact` | `count` | `Schema` | [官方](https://napcat.apifox.cn/226659190e0) | 获取最近会话。 |
| `adapter.napcat.account.get_rkey` | `get_rkey` | 无 | `无参` | [官方](https://napcat.apifox.cn/283136230e0) | 获取扩展 RKey。 |
| `adapter.napcat.account.get_rkey_server` | `get_rkey_server` | 无 | `无参` | [官方](https://napcat.apifox.cn/283136236e0) | 获取 RKey 服务器。 |
| `adapter.napcat.account.get_unidirectional_friend_list` | `get_unidirectional_friend_list` | 无 | `无参` | [官方](https://napcat.apifox.cn/266151878e0) | 获取单向好友列表。 |
| `adapter.napcat.account.internal_ocr_image` | `.ocr_image` | `image` | `Schema` | [官方](https://napcat.apifox.cn/226658234e0) | 内部 OCR 动作。 |
| `adapter.napcat.account.nc_get_rkey` | `nc_get_rkey` | 无 | `无参` | [官方](https://napcat.apifox.cn/226659297e0) | 获取 RKey。 |
| `adapter.napcat.account.ocr_image` | `ocr_image` | `image` | `Schema` | [官方](https://napcat.apifox.cn/226658231e0) | 图片 OCR 识别。 |
| `adapter.napcat.account.send_like` | `send_like` | `user_id`、`times` | `Schema` | [官方](https://napcat.apifox.cn/226656717e0) | 点赞。 |
| `adapter.napcat.account.set_diy_online_status` | `set_diy_online_status` | `face_id`、`face_type`、`wording` | `Schema` | [官方](https://napcat.apifox.cn/266151905e0) | 设置自定义在线状态。 |
| `adapter.napcat.account.set_friend_add_request` | `set_friend_add_request` | `flag`、`approve`、`remark` | `Schema` | [官方](https://napcat.apifox.cn/226656932e0) | 处理加好友请求。 |
| `adapter.napcat.account.set_friend_remark` | `set_friend_remark` | `user_id`、`remark` | `Schema` | [官方](https://napcat.apifox.cn/298305173e0) | 设置好友备注。 |
| `adapter.napcat.account.set_qq_avatar` | `set_qq_avatar` | `file` | `Schema` | [官方](https://napcat.apifox.cn/226658980e0) | 设置 QQ 头像。 |
| `adapter.napcat.account.set_self_longnick` | `set_self_longnick` | `longNick` | `Schema` | [官方](https://napcat.apifox.cn/226659186e0) | 设置个性签名。 |
| `adapter.napcat.account.translate_en2zh` | `translate_en2zh` | `words` | `Schema` | [官方](https://napcat.apifox.cn/226659102e0) | 英文单词翻译。 |

## 典型示例

```python
response = await self.ctx.api.call(
    "adapter.napcat.account.ocr_image",
    params={"image": "https://example.com/demo.png"},
)
```
