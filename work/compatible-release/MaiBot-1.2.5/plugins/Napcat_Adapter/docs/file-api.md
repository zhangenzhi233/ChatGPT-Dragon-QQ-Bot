# File 透传 API

这一页覆盖 `adapter.napcat.file.*` 下除 `get_record` 外的透传 API。

统一调用方式：

```python
response = await self.ctx.api.call(
    "adapter.napcat.file.upload_group_file",
    params={
        "group_id": 123456789,
        "file": "/tmp/demo.txt",
        "name": "demo.txt",
    },
)
```

字段来源说明：

- `无参`：官方页面当前无请求字段。
- `Schema`：直接来自官方“请求参数”结构。
- `Schema + 示例`：官方页左侧 Schema 和同页 `curl --data-raw` 示例合并后得到。
- `冲突`：官方页同页 Schema / 示例字段互相冲突，文档显式列出。

## API 列表

| API | 底层 action | 官方请求字段 | 来源 | 官方文档 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `adapter.napcat.file.cancel_online_file` | `cancel_online_file` | `user_id`、`msg_id` | `Schema` | [官方](https://napcat.apifox.cn/410334677e0) | 取消在线文件。 |
| `adapter.napcat.file.clean_stream_temp_file` | `clean_stream_temp_file` | 无 | `无参` | [官方](https://napcat.apifox.cn/395354124e0) | 清理流式传输临时文件。 |
| `adapter.napcat.file.create_flash_task` | `create_flash_task` | `files`、`name`、`thumb_path` | `Schema` | [官方](https://napcat.apifox.cn/410334666e0) | 创建闪传任务。 |
| `adapter.napcat.file.create_group_file_folder` | `create_group_file_folder` | `group_id`、`folder_name`、`name` | `Schema` | [官方](https://napcat.apifox.cn/226658773e0) | 创建群文件目录。 |
| `adapter.napcat.file.del_group_album_media` | `del_group_album_media` | `group_id`、`album_id`、`lloc` | `Schema` | [官方](https://napcat.apifox.cn/395455119e0) | 删除群相册媒体。 |
| `adapter.napcat.file.delete_group_file` | `delete_group_file` | `group_id`、`file_id` | `Schema` | [官方](https://napcat.apifox.cn/226658755e0) | 删除群文件。 |
| `adapter.napcat.file.delete_group_folder` | `delete_group_folder` | `group_id`、`folder_id`、`folder` | `Schema` | [官方](https://napcat.apifox.cn/226658779e0) | 删除群文件目录。 |
| `adapter.napcat.file.do_group_album_comment` | `do_group_album_comment` | `group_id`、`album_id`、`lloc`、`content` | `Schema` | [官方](https://napcat.apifox.cn/395458911e0) | 发表群相册评论。 |
| `adapter.napcat.file.download_file` | `download_file` | `url`、`base64`、`name`、`headers` | `Schema` | [官方](https://napcat.apifox.cn/226658887e0) | 下载文件。 |
| `adapter.napcat.file.download_file_image_stream` | `download_file_image_stream` | `file`、`file_id`、`chunk_size` | `Schema` | [官方](https://napcat.apifox.cn/395419462e0) | 下载图片文件流。 |
| `adapter.napcat.file.download_file_record_stream` | `download_file_record_stream` | `file`、`file_id`、`chunk_size`、`out_format` | `Schema` | [官方](https://napcat.apifox.cn/395417040e0) | 下载语音文件流。 |
| `adapter.napcat.file.download_file_stream` | `download_file_stream` | `file`、`file_id`、`chunk_size` | `Schema` | [官方](https://napcat.apifox.cn/395413859e0) | 下载文件流。 |
| `adapter.napcat.file.download_fileset` | `download_fileset` | `fileset_id` | `Schema` | [官方](https://napcat.apifox.cn/410334678e0) | 下载文件集。 |
| `adapter.napcat.file.get_file` | `get_file` | `file`、`file_id` | `Schema` | [官方](https://napcat.apifox.cn/226658985e0) | 获取文件。 |
| `adapter.napcat.file.get_fileset_id` | `get_fileset_id` | `share_code` | `Schema` | [官方](https://napcat.apifox.cn/410334679e0) | 获取文件集 ID。 |
| `adapter.napcat.file.get_fileset_info` | `get_fileset_info` | `fileset_id` | `Schema` | [官方](https://napcat.apifox.cn/410334671e0) | 获取文件集信息。 |
| `adapter.napcat.file.get_flash_file_list` | `get_flash_file_list` | `fileset_id` | `Schema` | [官方](https://napcat.apifox.cn/410334667e0) | 获取闪传文件列表。 |
| `adapter.napcat.file.get_flash_file_url` | `get_flash_file_url` | `fileset_id`、`file_name`、`file_index` | `Schema` | [官方](https://napcat.apifox.cn/410334668e0) | 获取闪传文件链接。 |
| `adapter.napcat.file.get_group_album_media_list` | `get_group_album_media_list` | `group_id`、`album_id`、`attach_info` | `Schema` | [官方](https://napcat.apifox.cn/395459066e0) | 获取群相册媒体列表。 |
| `adapter.napcat.file.get_group_file_system_info` | `get_group_file_system_info` | `group_id` | `Schema` | [官方](https://napcat.apifox.cn/226658789e0) | 获取群文件系统信息。 |
| `adapter.napcat.file.get_group_file_url` | `get_group_file_url` | `group_id`、`file_id`、`busid` | `Schema + 示例` | [官方](https://napcat.apifox.cn/226658867e0) | 官方页左侧 Schema 当前只列 `group_id` / `file_id`，同页示例请求体额外给出 `busid`。 |
| `adapter.napcat.file.get_group_files_by_folder` | `get_group_files_by_folder` | `group_id`、`folder_id`、`folder`、`file_count` | `Schema` | [官方](https://napcat.apifox.cn/226658865e0) | 获取群文件夹文件列表。 |
| `adapter.napcat.file.get_group_root_files` | `get_group_root_files` | `group_id`、`file_count` | `Schema` | [官方](https://napcat.apifox.cn/226658823e0) | 获取群根目录文件列表。 |
| `adapter.napcat.file.get_image` | `get_image` | `file`、`file_id` | `Schema` | [官方](https://napcat.apifox.cn/226657066e0) | 获取图片。 |
| `adapter.napcat.file.get_online_file_msg` | `get_online_file_msg` | `user_id` | `Schema` | [官方](https://napcat.apifox.cn/410334672e0) | 获取在线文件消息。 |
| `adapter.napcat.file.get_private_file_url` | `get_private_file_url` | `user_id`、`file_id` | `Schema + 示例` | [官方](https://napcat.apifox.cn/266151849e0) | 官方页左侧 Schema 当前只列 `file_id`，同页示例请求体额外给出 `user_id`。 |
| `adapter.napcat.file.get_qun_album_list` | `get_qun_album_list` | `group_id`、`attach_info` | `Schema` | [官方](https://napcat.apifox.cn/395460287e0) | 获取群相册列表。 |
| `adapter.napcat.file.get_share_link` | `get_share_link` | `fileset_id` | `Schema` | [官方](https://napcat.apifox.cn/410334670e0) | 获取文件分享链接。 |
| `adapter.napcat.file.move_group_file` | `move_group_file` | `group_id`、`file_id`、`current_parent_directory`、`target_parent_directory` | `Schema` | [官方](https://napcat.apifox.cn/283136359e0) | 移动群文件。 |
| `adapter.napcat.file.receive_online_file` | `receive_online_file` | `user_id`、`msg_id`、`element_id` | `Schema` | [官方](https://napcat.apifox.cn/410334675e0) | 接收在线文件。 |
| `adapter.napcat.file.refuse_online_file` | `refuse_online_file` | `user_id`、`msg_id`、`element_id` | `Schema` | [官方](https://napcat.apifox.cn/410334676e0) | 拒绝在线文件。 |
| `adapter.napcat.file.rename_group_file` | `rename_group_file` | `group_id`、`file_id`、`current_parent_directory`、`new_name` | `Schema` | [官方](https://napcat.apifox.cn/283136375e0) | 重命名群文件。 |
| `adapter.napcat.file.send_flash_msg` | `send_flash_msg` | `fileset_id`、`user_id`、`group_id` | `Schema` | [官方](https://napcat.apifox.cn/410334669e0) | 发送闪传消息。 |
| `adapter.napcat.file.send_online_file` | `send_online_file` | `user_id`、`file_path`、`file_name` | `Schema` | [官方](https://napcat.apifox.cn/410334673e0) | 发送在线文件。 |
| `adapter.napcat.file.send_online_folder` | `send_online_folder` | `user_id`、`folder_path`、`folder_name` | `Schema` | [官方](https://napcat.apifox.cn/410334674e0) | 发送在线文件夹。 |
| `adapter.napcat.file.set_group_album_media_like` | `set_group_album_media_like` | `group_id`、`album_id`、`lloc`、`id`、`set` | `Schema` | [官方](https://napcat.apifox.cn/395457331e0) | 点赞群相册媒体。 |
| `adapter.napcat.file.trans_group_file` | `trans_group_file` | `group_id`、`file_id` | `Schema` | [官方](https://napcat.apifox.cn/283136366e0) | 传输群文件。 |
| `adapter.napcat.file.upload_file_stream` | `upload_file_stream` | `stream_id`、`chunk_data`、`chunk_index`、`total_chunks`、`file_size`、`expected_sha256`、`is_complete`、`filename`、`reset`、`verify_only`、`file_retention` | `Schema` | [官方](https://napcat.apifox.cn/395363988e0) | 上传文件流。 |
| `adapter.napcat.file.upload_group_file` | `upload_group_file` | `group_id`、`file`、`name`、`folder`、`folder_id`、`upload_file` | `Schema` | [官方](https://napcat.apifox.cn/226658753e0) | 上传群文件。 |
| `adapter.napcat.file.upload_image_to_qun_album` | `upload_image_to_qun_album` | `group_id`、`album_id`、`album_name`、`file` | `Schema` | [官方](https://napcat.apifox.cn/395459739e0) | 上传图片到群相册。 |
| `adapter.napcat.file.upload_private_file` | `upload_private_file` | `user_id`、`file`、`name`、`upload_file` | `Schema` | [官方](https://napcat.apifox.cn/226658883e0) | 上传私聊文件。 |
| `adapter.napcat.file.test_download_stream` | `test_download_stream` | `error`、`url` | `冲突` | [官方](https://napcat.apifox.cn/395355338e0) | 官方页左侧 Schema 当前字段为 `error`，同页示例请求体却使用 `url`，两者互相冲突。 |

## 典型示例

```python
response = await self.ctx.api.call(
    "adapter.napcat.file.upload_group_file",
    params={
        "group_id": 123456789,
        "file": "/tmp/demo.txt",
        "name": "demo.txt",
    },
)
```
