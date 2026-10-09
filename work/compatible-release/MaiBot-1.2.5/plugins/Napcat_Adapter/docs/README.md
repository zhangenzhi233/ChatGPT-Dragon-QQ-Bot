# MaiBot NapCat Adapter API 文档

当前统计：

- 公开 API 总数：`164`
- 强类型封装 API：`24`
- 透传 NapCat action API：`140`
- 对照到 NapCat 官方文档的底层 action：`162 / 162`

## 文档索引

- [强类型封装 API](./typed-api.md)
- [System 透传 API](./system-api.md)
- [Account 透传 API](./account-api.md)
- [Group 透传 API](./group-api.md)
- [Message 透传 API](./message-api.md)
- [File 透传 API](./file-api.md)
- [核验与兼容性说明](./verification.md)

## 先看调用方式

### 强类型封装 API

这类 API 直接展开参数，不要再套一层 `params`。

```python
response = await self.ctx.api.call(
    "adapter.napcat.group.get_group_member_info",
    group_id=123456789,
    user_id=987654321,
    no_cache=True,
)
```

### 透传 NapCat action API

这类 API 统一只收 `params` 对象。

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

### 宿主统一返回结构

`self.ctx.api.call(...)` 返回的是宿主包装结构：

```python
{
    "success": True,
    "result": ...,
}
```

失败时通常为：

```python
{
    "success": False,
    "error": "...",
}
```

## 这次文档采用的对齐口径

- 透传 API 的“官方请求字段”优先看 NapCat 官方页面的“请求参数”结构。
- 如果官方页面左侧 Schema 没展开字段，改用同页 `curl --data-raw` 示例补齐。
- 如果官方页面 Schema 和 `curl` 示例同时给出、但字段不一致，文档会把冲突显式写出来，不会替官方文档做静默裁剪。
- 强类型封装 API 额外写清“适配器直接参数”和“实际下发给 NapCat 的 body”。

详细例外见 [核验与兼容性说明](./verification.md)。

- NapCat 官方文档地址：[https://napcat.apifox.cn/](https://napcat.apifox.cn/)

## 命名空间数量

| 命名空间 | 数量 | 说明 |
| --- | ---: | --- |
| `adapter.napcat.action` | 2 | 适配器提供的通用动作入口。 |
| `adapter.napcat.system` | 23 | 登录、状态、凭证、系统控制。 |
| `adapter.napcat.account` | 27 | 资料、好友、收藏、OCR、账号能力。 |
| `adapter.napcat.group` | 41 | 群、频道、公告、群管理。 |
| `adapter.napcat.message` | 28 | 消息、互动、转发、AI 语音。 |
| `adapter.napcat.file` | 43 | 文件、群文件、在线文件、相册、流式传输。 |
