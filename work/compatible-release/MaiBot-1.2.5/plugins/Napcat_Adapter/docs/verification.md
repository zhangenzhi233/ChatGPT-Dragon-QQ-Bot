# 核验与兼容性说明

## 1. 这次核验做了什么

- 扫描 `plugins/MaiBot-Napcat-Adapter/apis/*.py` 中全部 `@API(..., public=True)` 公开接口。
- 对每个透传 API 反查其底层 NapCat action。
- 用 NapCat 官方文档 [https://napcat.apifox.cn/](https://napcat.apifox.cn/) 逐项确认底层 action 页面是否存在。
- 用浏览器逐页读取官方页面的“请求参数”结构；遇到官方页左侧只显示泛型 `object` 时，再补读同页 `curl --data-raw` 示例。
- 对请求示例少于隐藏 schema 的页面，额外抓取官方页原始 HTML，核对 Apifox 内嵌的 request body schema。
- 对强类型封装 API，额外对照 `plugins/MaiBot-Napcat-Adapter/services/query_service.py` 确认适配器实际下发的 body。

## 2. 覆盖范围

- 适配器公开 API 总数：`164`
- 其中适配器自带通用入口：`2`
  - `adapter.napcat.action.call`
  - `adapter.napcat.action.call_data`
- 其中可映射到底层 NapCat action 的 API：`162`
- 这 `162` 个底层 action 的官方文档页面：`162 / 162` 都已找到并写入 docs

## 3. 参数对齐口径

- 普通透传 API：文档写“官方请求字段”，适配器自己不裁剪，只要求调用方传 `params={...}`。
- 强类型封装 API：文档写“适配器直接参数”和“官方请求字段”两列，明确哪里是适配器收敛过的用法。
- 如果官方页 `Schema` 和同页 `curl` 示例不一致，文档不会替官方做静默判断，而是显式标成 `Schema + 示例` 或 `冲突`。

## 4. 已确认的官方页例外

| action / API | 官方文档 | 现象 | 文档处理方式 |
| --- | --- | --- | --- |
| `get_online_clients` | [官方](https://napcat.apifox.cn/226657379e0) | 左侧 Schema 只显示 `object`，同页示例请求体给出 `no_cache` | 在文档中按 `示例` 记录 `no_cache` |
| `_set_model_show` | [官方](https://napcat.apifox.cn/227233993e0) | 左侧 Schema 只显示 `object`，同页示例请求体给出 `model`、`model_show` | 在文档中按 `示例` 记录 |
| `get_mini_app_ark` | [官方](https://napcat.apifox.cn/227738594e0) | 官方页为 `Any Of` 结构，但左侧 Schema 未展开可直接抄用的顶层字段 | 在文档中按同页示例请求体记录当前可见字段 |
| `get_guild_service_profile` | [官方](https://napcat.apifox.cn/226659317e0) | 左侧 Schema 只显示 `object`，同页示例请求体给出 `guild_id` | 在文档中按 `示例` 记录 `guild_id` |
| `get_group_file_url` | [官方](https://napcat.apifox.cn/226658867e0) | 左侧 Schema 只列 `group_id`、`file_id`，同页示例请求体额外给出 `busid` | 在文档中按 `Schema + 示例` 合并记录 |
| `get_private_file_url` | [官方](https://napcat.apifox.cn/266151849e0) | 左侧 Schema 只列 `file_id`，同页示例请求体额外给出 `user_id` | 在文档中按 `Schema + 示例` 合并记录 |
| `test_download_stream` | [官方](https://napcat.apifox.cn/395355338e0) | 左侧 Schema 当前字段为 `error`，同页示例请求体却使用 `url` | 在文档中标记为 `冲突`，两组字段都写出 |
| `get_stranger_info` | [官方](https://napcat.apifox.cn/226656970e0) | 页面默认示例只写 `user_id`，但原始 HTML 的隐藏 schema 还定义了 `no_cache` | 在文档和实现中按隐藏 schema 记录 `user_id`、`no_cache` |
| `get_forward_msg` | [官方](https://napcat.apifox.cn/226656712e0) | 页面默认示例只写 `message_id`，但原始 HTML 的隐藏 schema 还定义了 `id` | 在文档和实现中按隐藏 schema 同时支持 `message_id`、`id` |
| `get_record` | [官方](https://napcat.apifox.cn/226657058e0) | 页面默认示例只写 `file`、`out_format`，但原始 HTML 的隐藏 schema 还定义了 `file_id` | 在文档和实现中按隐藏 schema 记录 `file`、`file_id`、`out_format` |
| `send_poke` | [官方](https://napcat.apifox.cn/250286923e0) | 页面默认示例只写 `user_id`，但原始 HTML 的隐藏 schema 还定义了 `group_id`、`target_id` | 在文档和实现中按隐藏 schema 记录 `user_id`、`group_id`、`target_id` |
| `send_group_sign` | [官方](https://napcat.apifox.cn/230897177e0) | 官方页面存在，但侧边序列化索引缺少常规标题字段 | 文档直接写死官方链接，不依赖侧边索引标题 |
| `send_poke` / `friend_poke` / `forward_group_single_msg` / `send_ark_share` / `send_group_ark_share` / `clean_stream_temp_file` | 对应各自官方页 | 官方侧边序列化索引缺少常规标题字段，但页面本身存在 | 文档直接写死官方链接，不依赖侧边索引标题 |

## 5. 适配器实现侧的对齐与兼容策略

| API | 实际下发 | 与官方字段的关系 |
| --- | --- | --- |
| `adapter.napcat.message.send_poke` | `{"user_id": ..., "group_id"?: ..., "target_id"?: ...}` | 已对齐官方隐藏 schema；公开 API 额外保留 `qq_id` 作为旧版兼容别名 |
| `adapter.napcat.message.get_forward_msg` | 调 `get_forward_msg({"message_id"?: ..., "id"?: ...})` | 已对齐官方隐藏 schema；至少提供一个字段，双字段同时传入时要求一致 |
| `adapter.napcat.file.get_record` | 调 `get_record({"file"?: ..., "file_id"?: ..., "out_format"?: ...})` | 已对齐官方隐藏 schema；默认 `out_format="wav"` 仅用于兼容旧行为 |
| `adapter.napcat.account.get_stranger_info` | `{"user_id": ..., "no_cache": ...}` | 已对齐官方隐藏 schema；`no_cache` 默认值为 `False` |

- 当前强类型封装 API 已无“缺少官方字段”的已知冲突项。
- 当前仍保留的兼容策略只有两类：`send_poke` 的 `qq_id` 旧版别名，以及 `get_record` 的 `out_format="wav"` 默认值。
