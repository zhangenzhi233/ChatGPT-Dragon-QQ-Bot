"""为 Planner 和 Replyer 提供一致、随当前配置更新的角色身份。"""

from src.common.i18n import get_locale
from src.config.config import global_config
from src.config.official_configs import build_personality_emotion_suffix


def build_current_personality_prompt() -> str:
    """读取当前昵称和人设，明确历史发言不能覆盖当前身份。"""

    bot_name = global_config.bot.nickname.strip()
    if not bot_name:
        raise ValueError("bot.nickname 不能为空，无法构建当前角色身份。")
    aliases = [name.strip() for name in global_config.bot.alias_names if name.strip()]
    localized_rules = {
        "zh-CN": (
            f"当前角色的唯一昵称是 {bot_name}。",
            "当前配置的人设优先于历史自我介绍、聊天摘要、表情文字和工具提供的回复参考。"
            "不得依据旧聊天记录把当前昵称纠正成旧名字。只有下方明确列出的别名可以作为自称；"
            "没有配置别名时，不得自行创造其他昵称。",
            "已配置别名：" + ("、".join(aliases) if aliases else "无"),
            "表情的情绪标签不能证明图中人物的外观、身份或用户真实心情。"
            "只有角色索引确认属于当前角色的图片才能称为自己的形象；展示自己的表情时，"
            "attach_emoji 使用当前角色名加简短情绪或动作。其他人物、猫耳或同样白发的角色不能冒充本人。"
            "看图按实际可见的动作和文字描述，不把一个梗强行解释为用户疲惫或伤心。",
        ),
        "en-US": (
            f"The character's current name is {bot_name}.",
            "The current configured persona takes precedence over earlier introductions, chat summaries, "
            "sticker text, and tool-provided reply references. Never correct the current name to an old "
            "name found in chat history. Only the explicitly configured aliases below may be used as "
            "self-identification; do not invent another nickname when no alias is configured.",
            "Configured aliases: " + (", ".join(aliases) if aliases else "none"),
            "Emotion tags do not establish a sticker character's appearance or identity, or the user's feelings. "
            "Only images verified by the character catalog may represent the current character. To show your own "
            "sticker, use the current character name plus a short emotion or action in attach_emoji. Other characters "
            "must not be presented as yourself. Describe visible actions and text without asserting the user's mood.",
        ),
        "ja-JP": (
            f"現在のキャラクター名は {bot_name} です。",
            "現在設定されている人物設定は、過去の自己紹介、会話の要約、スタンプの文字、"
            "ツールが提供する返信参考情報より優先されます。過去の会話を根拠に現在の名前を"
            "以前の名前へ訂正してはいけません。自称に使える別名は以下に明示されたものだけです。"
            "別名が設定されていない場合、新しい愛称を勝手に作らないでください。",
            "設定済みの別名：" + ("、".join(aliases) if aliases else "なし"),
            "スタンプの感情タグだけでは人物の外見や正体、ユーザーの気持ちは分かりません。"
            "自分の姿として示せるのはキャラクター索引で確認済みの画像だけです。自分のスタンプを示すときは、"
            "attach_emoji に現在のキャラクター名と短い感情または動作を指定してください。別の人物を自分として"
            "紹介せず、見える動作や文字を説明し、ユーザーの気分を断定しないでください。",
        ),
    }
    prompt_lines = list(localized_rules.get(get_locale(), localized_rules["zh-CN"]))
    personality = global_config.personality.personality.strip()
    if personality:
        prompt_lines.append(personality)
    emotion_suffix = build_personality_emotion_suffix(global_config.experimental.emotion_trait)
    if emotion_suffix:
        prompt_lines.append(emotion_suffix)
    return "\n".join(prompt_lines)
