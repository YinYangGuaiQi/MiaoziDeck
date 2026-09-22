# 开发与构建

准备 Node.js 20+、npm、Python 3.10+：

```sh
npm ci
npx tsc --noEmit
npm run build
python3 scripts/package_release.py --assets-dir /path/to/runtime-assets --official-dir /path/to/official-runtime --decky-dir /path/to/decky-runtime
```

运行资源的来源与目录要求见 [第三方资源](THIRD_PARTY.md)。输出位于 `release/`，包含双击安装用 `.desktop`、在线安装用 `.sh`、对应 SHA-256 文件与打包用 ZIP。GitHub 自动生成的 Source code ZIP 不能直接安装。

推荐从 [Latest](https://github.com/YinYangGuaiQi/MiaoziDeck/releases/latest) 下载 `.desktop` 安装文件，从任意文件夹双击运行。它将完整 `.sh` 安装程序编码为 Desktop Entry 注释，通过 `%k` 获取自身位置，校验后在临时目录启动安装。无需旁边放置其他文件，也无需额外下载运行组件。安装窗口会保留完成或错误信息。

仓库根目录的 `install.sh` 是在线下载入口，默认获取 Latest，自动下载并校验 `.sh` 后运行。Release 显示名称不参与版本识别，修改名称不会影响安装；可通过 `--version v0.1.0-alpha.9` 固定版本。保留 `.sh` 供在线或命令行使用，不把手动输入终端命令作为默认安装流程。`.desktop.sha256` 可供额外校验，双击安装不要求下载它。

桌面入口采用 [Desktop Entry 规范](https://specifications.freedesktop.org/desktop-entry/latest/exec-variables.html)。系统的信任确认和管理员密码仍由用户处理；浏览器若追加 `.download` 后缀，需要去掉后缀。约 120 MiB 自包含入口在 SteamOS 3.8.16 的启动表现尚待真机验证。

| 文件 | 用途 |
| --- | --- |
| `src/index.tsx` | Decky 界面 |
| `main.py` | 账号、订阅及插件接口 |
| `bootstrap_profile.py` | 新用户隔离初始化 |
| `native_subscription.py` | 内置组件同步订阅 |
| `acceleration_service.py` | 独立后台加速服务 |
| `core_session.py` / `cache_nodes.py` | 内核通信与节点解析 |
| `install.sh` | 在线安装入口 |
| `scripts/desktop_package.py` / `scripts/desktop_launch.py` | 生成及启动双击安装文件 |
| `scripts/` | 打包、自解压及安装脚本 |

GitHub 上按普通 Release 发布并设为 Latest，版本仍为 alpha 测试版，尚未完成全新 Steam Deck 真机验证。本地检查不能替代真实 SteamOS 的全新安装、首次登录和自动安装 Decky 测试。发布流程见 [发布说明](PUBLISHING.md)。
