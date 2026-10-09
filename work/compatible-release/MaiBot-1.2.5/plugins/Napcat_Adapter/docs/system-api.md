# System 透传 API

这一页覆盖 `adapter.napcat.system.*` 下除 `get_login_info` 外的透传 API。

统一调用方式：

```python
response = await self.ctx.api.call(
    "adapter.napcat.system.check_url_safely",
    params={"url": "https://example.com"},
)
```

字段来源说明：

- `无参`：官方页面当前无请求字段。
- `Schema`：直接来自官方“请求参数”结构。
- `示例`：官方页面 Schema 只显示泛型 `object`，字段来自同页 `curl --data-raw` 示例。

## API 列表

| API | 底层 action | 官方请求字段 | 来源 | 官方文档 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `adapter.napcat.system.bot_exit` | `bot_exit` | 无 | `无参` | [官方](https://napcat.apifox.cn/283136399e0) | 退出登录。 |
| `adapter.napcat.system.can_send_image` | `can_send_image` | 无 | `无参` | [官方](https://napcat.apifox.cn/226657071e0) | 是否可以发送图片。 |
| `adapter.napcat.system.can_send_record` | `can_send_record` | 无 | `无参` | [官方](https://napcat.apifox.cn/226657080e0) | 是否可以发送语音。 |
| `adapter.napcat.system.check_url_safely` | `check_url_safely` | `url` | `Schema` | [官方](https://napcat.apifox.cn/228534361e0) | 检查 URL 安全性。 |
| `adapter.napcat.system.clean_cache` | `clean_cache` | 无 | `无参` | [官方](https://napcat.apifox.cn/298305106e0) | 清理缓存。 |
| `adapter.napcat.system.get_credentials` | `get_credentials` | `domain` | `Schema` | [官方](https://napcat.apifox.cn/226657054e0) | 获取登录凭证。 |
| `adapter.napcat.system.get_csrf_token` | `get_csrf_token` | 无 | `无参` | [官方](https://napcat.apifox.cn/226657044e0) | 获取 CSRF Token。 |
| `adapter.napcat.system.get_doubt_friends_add_request` | `get_doubt_friends_add_request` | `count` | `Schema` | [官方](https://napcat.apifox.cn/289565516e0) | 获取可疑好友申请。 |
| `adapter.napcat.system.get_model_show` | `_get_model_show` | `model` | `Schema` | [官方](https://napcat.apifox.cn/227233981e0) | 获取机型显示。 |
| `adapter.napcat.system.get_online_clients` | `get_online_clients` | `no_cache` | `示例` | [官方](https://napcat.apifox.cn/226657379e0) | 官方页左侧 Schema 当前只显示 `object`，同页示例请求体给出 `no_cache`。 |
| `adapter.napcat.system.get_robot_uin_range` | `get_robot_uin_range` | 无 | `无参` | [官方](https://napcat.apifox.cn/226658975e0) | 获取机器人 UIN 范围。 |
| `adapter.napcat.system.get_status` | `get_status` | 无 | `无参` | [官方](https://napcat.apifox.cn/226657083e0) | 获取运行状态。 |
| `adapter.napcat.system.get_version_info` | `get_version_info` | 无 | `无参` | [官方](https://napcat.apifox.cn/226657087e0) | 获取版本信息。 |
| `adapter.napcat.system.nc_get_packet_status` | `nc_get_packet_status` | 无 | `无参` | [官方](https://napcat.apifox.cn/226659280e0) | 获取 Packet 状态。 |
| `adapter.napcat.system.nc_get_user_status` | `nc_get_user_status` | `user_id` | `Schema` | [官方](https://napcat.apifox.cn/226659292e0) | 获取用户在线状态。 |
| `adapter.napcat.system.send_packet` | `send_packet` | `cmd`、`data`、`rsp` | `Schema` | [官方](https://napcat.apifox.cn/250286903e0) | 发送原始数据包。 |
| `adapter.napcat.system.set_doubt_friends_add_request` | `set_doubt_friends_add_request` | `flag`、`approve` | `Schema` | [官方](https://napcat.apifox.cn/289565525e0) | 处理可疑好友申请。 |
| `adapter.napcat.system.set_input_status` | `set_input_status` | `user_id`、`event_type` | `Schema` | [官方](https://napcat.apifox.cn/226659225e0) | 设置输入状态。 |
| `adapter.napcat.system.set_model_show` | `_set_model_show` | `model`、`model_show` | `示例` | [官方](https://napcat.apifox.cn/227233993e0) | 官方页左侧 Schema 当前只显示 `object`，同页示例请求体给出 `model` / `model_show`。 |
| `adapter.napcat.system.set_online_status` | `set_online_status` | `status`、`ext_status`、`battery_status` | `Schema` | [官方](https://napcat.apifox.cn/226658977e0) | 设置在线状态。 |
| `adapter.napcat.system.set_restart` | `set_restart` | 无 | `无参` | [官方](https://napcat.apifox.cn/410334662e0) | 重启服务。 |
| `adapter.napcat.system.unknown_action` | `unknown` | 无 | `无参` | [官方](https://napcat.apifox.cn/411631224e0) | 透传调用名为 `unknown` 的底层动作。 |

## 典型示例

```python
response = await self.ctx.api.call(
    "adapter.napcat.system.get_online_clients",
    params={"no_cache": False},
)
```
