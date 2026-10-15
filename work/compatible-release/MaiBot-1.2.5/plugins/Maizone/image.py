import random
import base64
import asyncio
from io import BytesIO
from PIL import Image
from pathlib import Path
from openai import OpenAI
import requests

class NoLogger:
    def info(self, msg):
        pass
    def warning(self, msg):
        pass
    def error(self, msg):
        pass
    def debug(self, msg):
        pass
logger = NoLogger()
def set_image_logger(custom_logger):
    global logger
    logger = custom_logger

plugin_context = None
def set_images_plugin_context(ctx):
    global plugin_context
    plugin_context = ctx
    set_image_logger(ctx.ctx.logger)

async def generate_image(
    base_url: str,
    api_key: str,
    model: str,
    prompt: str,
    reference: str | None = None,
) -> bytes:
    """
    Openai格式生成一张图片并返回其 bytes。
    参数:
        - base_url: AI生图服务地址
        - api_key: AI生图服务API Key
        - model: AI生图模型
        - prompt: 图片生成提示
        - reference: 参考图URL或本地路径
    返回:
        - 图片的二进制数据
    """
    body = {
        "model": model,
        "prompt": prompt,
        "n": 1,  # 强制只生成一张
    }
    if reference is not None:
        # 判断是URL还是本地路径
        if reference.startswith("http://") or reference.startswith("https://"):
            # 直接使用URL作为参考图
            body["extra_body"] = {
                "image": reference
            }
        else:
            # 读取本地文件并转换为base64
            path = Path(reference)
            with open(str(path.absolute()), "rb") as f:
                img_data = f.read()
            format = path.suffix[1:].lower() if path.suffix else "png"
            encoded_string = base64.b64encode(img_data).decode('utf-8')
            body["extra_body"] = {
                "image": f"data:image/{format};base64,{encoded_string}"
            }

    client = OpenAI(base_url=base_url, api_key=api_key)
    logger.info(f"正在使用模型 {model} 生成图片: {prompt}")
    response = client.images.generate(**body)
    if response is None or not response.data:
        logger.error("图片生成失败，未收到有效响应")
        return b''
    
    img = response.data[0]
    if img.url:
        logger.info("下载图片中...")
        r = requests.get(img.url, timeout=30)
        r.raise_for_status()
        return r.content
    elif img.b64_json:
        logger.info("解码 base64 图片...")
        return base64.b64decode(img.b64_json)
    else:
        raise ValueError("图片数据为空")

async def generate_ai_images(message: str, image_number: int) -> list[bytes]:
    """根据message生成指定数量的AI图片，返回图片的二进制数据列表"""
    images = []
    images_prompt = []  # 已使用过的配图
    for _ in range(image_number):
        image_bytes = await generate_ai_image(message, images_prompt)
        images.append(image_bytes)
    return images


async def generate_ai_image(message: str, images_prompt: list[str] | None = None) -> bytes:
    """生成单张 AI 图片并返回二进制数据。

    Args:
        message: 用于生成图片的上下文文本
        images_prompt: 可选的已使用提示词列表（会在生成后追加新的提示词）

    Returns:
        bytes: 图片二进制数据
    """
    # 获取配置
    personality = plugin_context.personality  # type: ignore
    base_url = plugin_context.config.image.base_url  # type: ignore
    api_key = plugin_context.config.image.api_key  # type: ignore
    model = plugin_context.config.image.model  # type: ignore
    text_model = plugin_context.config.plugin.text_model  # type: ignore
    enable_reference = plugin_context.config.image.enable_reference  # type: ignore
    reference = plugin_context.config.image.reference if enable_reference else None  # type: ignore
    prompt_template = plugin_context.config.image.prompt  # type: ignore
    ref_prompt = plugin_context.config.image.ref_prompt if enable_reference else ""  # type: ignore

    used = images_prompt if images_prompt is not None else []
    # 构建提示词
    prompt = prompt_template.format(personality=personality, message=message) + ref_prompt
    prompt += f"已使用过的配图提示词：{used if used else '无'}。"
    response = await plugin_context.ctx.llm.generate(prompt, task_name=text_model)  # type: ignore
    image_prompt = response.get("response", "")
    logger.info(f"生成的图片提示词：{image_prompt}")
    if images_prompt is not None:
        images_prompt.append(image_prompt)

    # 生成图片
    image_bytes = await generate_image(base_url, api_key, model, image_prompt, reference)
    return image_bytes

# 配图选择使用的常见情绪/动作关键词，从正文中提取短标签查询已有表情素材。
_EMOTION_KEYWORDS = (
    "开心", "高兴", "快乐", "微笑", "大笑", "难过", "伤心", "哭泣", "委屈",
    "生气", "愤怒", "惊讶", "震惊", "思考", "疑惑", "害羞", "脸红",
    "日常", "睡觉", "晚安", "早安", "加油", "打气", "点赞", "比心", "挥手",
    "打招呼", "谢谢", "抱歉", "得意", "骄傲", "发呆", "叹气", "放松", "悠闲",
    "元气", "可爱", "帅气", "温柔", "平静", "期待", "兴奋", "疲惫",
    "关心", "安慰", "休息", "问候", "鼓励",
)
# 无匹配时使用的受控通用角色标签，作为明确策略而不是随机拉陌生图。
_CHARACTER_GENERIC_TAGS = ("问候",)


async def _resolve_character_name() -> str:
    """解析当前角色名（优先从主程序 bot 配置读取）。"""
    try:
        bot = await plugin_context.ctx.config.get("bot", {})
        nickname = str((bot or {}).get("nickname") or "").strip()
        if nickname:
            return nickname
    except Exception as exc:
        logger.warning(f"读取当前角色名失败：{exc}")
    return ""


async def _emoji_description_to_bytes(description: str) -> bytes | None:
    """按短标签查询表情素材，并校验返回的 base64 非空。"""
    try:
        emoji = await plugin_context.ctx.emoji.get_by_description(description=description)
    except Exception as exc:
        logger.warning(f"查询配图标签失败：{description}：{exc}")
        return None
    if not isinstance(emoji, dict):
        return None
    base64_data = emoji.get("base64", "")
    if not base64_data:
        return None
    try:
        image_bytes = base64.b64decode(base64_data, validate=True)
        with Image.open(BytesIO(image_bytes)) as image:
            image.verify()
    except Exception as exc:
        logger.warning(f"解码配图失败：{description}：{exc}")
        return None
    return image_bytes if image_bytes else None


async def generate_emoji_image(message: str) -> bytes | None:
    """从正文提取情绪/角色短标签，选取已有银白龙表情素材作为配图。

    不再用整段正文查图（长文必然查不到）；候选必须文件可读、bytes 非空；
    无匹配时选用已有角色的“问候”素材，仍无匹配则明确返回 None。
    """
    character_name = await _resolve_character_name()
    if not character_name:
        logger.error("无法确认当前角色，拒绝选择配图")
        return None

    matched_keywords = [kw for kw in _EMOTION_KEYWORDS if kw in message]
    matched_keywords.sort(key=len, reverse=True)

    candidates: list[str] = []

    def _add(candidate: str) -> None:
        candidate = (candidate or "").strip()
        if candidate and candidate not in candidates:
            candidates.append(candidate)

    for keyword in matched_keywords:
        _add(f"{character_name} {keyword}")
    for generic in _CHARACTER_GENERIC_TAGS:
        _add(f"{character_name} {generic}")

    if not candidates:
        logger.error(f"正文未提取到可用情绪标签，且无可用通用标签：{message[:30]!r}")
        return None

    for description in candidates:
        image_bytes = await _emoji_description_to_bytes(description)
        if image_bytes:
            logger.info(f"配图命中标签：{description}")
            return image_bytes
        logger.debug(f"配图标签无可用素材：{description}")

    logger.error(f"未找到可用配图：正文标签={matched_keywords} 角色={character_name or '无'}")
    return None

async def generate_emoji_images(message: str, number: int) -> list[bytes]:
    """根据message生成指定数量的表情包图片，返回图片的二进制数据列表"""
    images = []
    for _ in range(number):
        image = await generate_emoji_image(message)
        if image:
            images.append(image)
    return images

async def generate_images(message: str, image_mode: str = "only_emoji", image_number: int = 1, ai_probability: float = 0.5) -> list[bytes]:
    """根据message生成图片
    image_mode: only_emoji（仅表情包）、only_ai（仅AI生成）、random（随机）
    ai_probability: 当image_mode为random时，生成AI图片的概率，取值范围0-1
    """
    images_list: list[bytes] = []
    if image_mode == "only_emoji":
        # 仅表情包
        images_list = await generate_emoji_images(message, image_number)
    elif image_mode == "only_ai":
        # 仅AI生成
        images_list = await generate_ai_images(message, image_number)
    elif image_mode == "random":
        # 随机
        for _ in range(image_number):
            if random.random() < ai_probability:
                image_bytes = await generate_ai_image(message)
                if image_bytes:
                    images_list.append(image_bytes)
            else:
                emoji_bytes = await generate_emoji_image(message)
                if emoji_bytes:
                    images_list.append(emoji_bytes)
    else:
        logger.error(f"未知的image_mode：{image_mode}")
        return []
    return images_list

def test_generate_images():
    # 测试AI生图功能
    baseurl = "https://ark.cn-beijing.volces.com/api/v3"
    apikey = "your_api_key"
    model = "doubao-seedream-5-0-260128"
    prompt = "生成人物全身照"
    reference = r"D:\IE\QQbot\MaiBot-1.0.0-pre.15\plugins\maizone\reference.jpg"
    image_bytes = asyncio.run(generate_image(baseurl, apikey, model, prompt, reference))
    with open("test_ai_image.png", "wb") as f:
        f.write(image_bytes)

if __name__ == "__main__":
    test_generate_images()
