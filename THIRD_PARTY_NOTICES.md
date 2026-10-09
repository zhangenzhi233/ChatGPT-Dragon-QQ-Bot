# 第三方来源与许可

本文件说明组件来源与许可边界，不能替代各目录中完整的 LICENSE/NOTICE。根目录 GPL v3 适用于本项目整合脚本与相应 MaiBot 修改，不覆盖下列独立许可。

| 组件 | 来源 / 版本 | 许可及文件 |
|---|---|---|
| MaiBot | [Mai-with-u/MaiBot](https://github.com/Mai-with-u/MaiBot)，1.2.5 | `work/compatible-release/MaiBot-1.2.5/LICENSE`，GPL v3；EULA 与 PRIVACY 原文保留，使用者自己阅读确认 |
| A_memorix | MaiBot 自带 | 默认 AGPL v3，并保留 `LICENSE-MAIBOT-GPL.md` 对 MaiBot 项目上下文的 GPL 特别授权；不能把该授权外推至其他用途 |
| MaiBot dashboard | MaiBot 自带 | `dashboard/LICENSE`，AGPL v3 |
| llm_models | MaiBot 自带 | `src/llm_models/LICENSE`，MIT，原作者声明保留 |
| NapCat Adapter | [Mai-with-u/MaiBot-Napcat-Adapter](https://github.com/Mai-with-u/MaiBot-Napcat-Adapter)，1.4.0 | manifest 声明 GPL v3 或更高版本，本包附完整 GPL v3 文本 |
| Maizone | [internetsb/Maizone](https://github.com/internetsb/Maizone)，3.0.3 | MIT，原版权声明保留；本项目把插件默认开关改为关闭 |
| SilverDragonVoice / Companion | 本项目独立定制，1.0.0 | MIT；各插件目录附 LICENSE |
| Sign in with ChatGPT DevKit | [openai/sign-in-with-chatgpt-devkit](https://github.com/openai/sign-in-with-chatgpt-devkit)，本地保存的 0.1.0 源码快照 | Noncommercial License v1.0；源目录、local 包均保留完整许可及第三方声明 |
| NapCat | [NapNeko/NapCatQQ](https://github.com/NapNeko/NapCatQQ)，4.18.33 | 本仓库不分发其程序，安装时从官方发行地址下载；下载包的许可声明保留，以官方发行包为准 |

上游源码快照 SHA256、MaiBot 的 12 处原有修改和 SDK 的 2 处原有修改列于 [source-changes.json](docs/source-changes.json)。本包另保留两个新增核心模块和 SDK 的 raw Responses 模块及测试；修改的 SDK 源文件顶部附变更声明，修改仍受同一非商业许可约束。

SDK 第 5 条不授予 OpenAI 商标或服务访问权。登录能力、账号资格、额度和服务规则由 OpenAI 决定。本项目不共享任何维护者账户或登录令牌。

Python 和 Node 依赖由使用者安装，不将虚拟环境或 node_modules 上传。Python 主依赖由原 uv.lock 固定；额外插件依赖见 Maizone/requirements.txt 与 edge-tts==7.2.8。SDK 使用原 package-lock.json。

本项目保留源码以便核验和复现，不承诺整套组合适合商业使用。图片素材另见 assets/README.md，不适用代码许可证。

