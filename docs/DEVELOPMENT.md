# 开发与构建

准备 Node.js 20+、npm、Python 3.10+：

```sh
npm ci
npx tsc --noEmit
npm run build
python3 scripts/package_release.py --assets-dir /path/to/runtime-assets --official-dir /path/to/official-runtime --decky-dir /path/to/decky-runtime
```

运行资源的来源与目录要求见 [第三方资源](THIRD_PARTY.md)。输出位于 `release/`，包含单文件 `.sh` 安装包、SHA-256 文件与打包用 ZIP。GitHub 自动生成的 Source code ZIP 不能直接安装。

完整安装文件为 `MiaoziDeck-0.1.0-alpha.9.sh`，已内置全部安装资源，直接用 `bash 文件名.sh` 运行即可。仓库根目录的 `install.sh` 是在线下载入口，会下载并运行同一完整安装文件；`.sh.sha256` 是在线安装所用的校验文件，手动安装只需下载完整 `.sh` 文件。

| 文件 | 用途 |
| --- | --- |
| `src/index.tsx` | Decky 界面 |
| `main.py` | 账号、订阅及插件接口 |
| `bootstrap_profile.py` | 新用户隔离初始化 |
| `native_subscription.py` | 内置组件同步订阅 |
| `acceleration_service.py` | 独立后台加速服务 |
| `core_session.py` / `cache_nodes.py` | 内核通信与节点解析 |
| `install.sh` | 在线安装入口 |
| `scripts/` | 打包、自解压及安装脚本 |

GitHub 上按普通 Release 发布并设为 Latest，版本仍为 alpha 测试版，尚未完成全新 Steam Deck 真机验证。本地检查不能替代真实 SteamOS 的全新安装、首次登录和自动安装 Decky 测试。发布流程见 [发布说明](PUBLISHING.md)。
