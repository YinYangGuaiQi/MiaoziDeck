# 喵子 Deck / Miaozi Deck

在 Steam Deck 游戏模式中登录喵子账号、同步订阅和管理网络加速的非官方 Decky 插件。

**alpha.9 完整安装候选版：所有安装资源已合并到一个文件；全新设备上的首次登录与自动初始化尚待 Steam Deck 实测，暂不要作为已验证的稳定版本发布。**

仓库：[Mlietial/MiaoziDeck](https://github.com/Mlietial/MiaoziDeck)。当前为私有仓库，源码和 Release 仅对获授权的 GitHub 账号可见。

## 特点

- **一个文件装完整**：内置订阅组件、加速内核、依赖库和 Yacd 仪表盘，不要求用户另装、打开或提前登录原版喵子客户端。
- **自动准备 Decky**：已有 Decky 时保留现有版本；未安装时自动部署包内的 Decky Loader。
- **插件内登录**：登录后同步订阅，已有订阅时隐藏账号密码表单。
- **后台持续加速**：后台服务独立于 Steam 和 Decky，切换桌面模式和游戏模式后继续运行。
- **节点仪表盘**：通过本机 Yacd 页面选节点、测速和查看连接。
- **简洁设置**：左侧选择订阅与账号、加速设置或帮助与诊断，右侧显示对应控制。

## 安装：二选一

### 一个文件

登录有权限的 GitHub 账号，从 [alpha.9 Release](https://github.com/Mlietial/MiaoziDeck/releases/tag/v0.1.0-alpha.9) 下载附件 `MiaoziDeck-0.1.0-alpha.9.run`，放到 Deck 的下载目录，在桌面模式终端运行：

```sh
bash ~/Downloads/MiaoziDeck-0.1.0-alpha.9.run
```

无需解压、设置执行权限或另下载依赖。安装资源已包含在文件中，安装阶段可以离线执行；登录和加速需要联网。提示时输入 Deck 本机管理员密码。

### 一条在线命令（仓库公开后启用）

```sh
curl -fL --proto '=https' https://raw.githubusercontent.com/Mlietial/MiaoziDeck/main/install.sh -o /tmp/miaozi-deck-install.sh && bash /tmp/miaozi-deck-install.sh --version v0.1.0-alpha.9
```

**当前私有仓库不支持匿名 curl 安装，请使用上面的单文件方式。** 将来由仓库所有者改为公开后，用户可以直接复制此命令，无需修改地址；脚本会自动下载完整安装文件、校验并安装。不要把 GitHub 访问令牌粘贴到公开命令或项目说明中。

## 安装后

回到游戏模式，打开 **… → Decky → Miaozi Deck → 设置 → 订阅与账号**，登录自己的喵子账号，然后开启加速。账号登录属于正常使用，不是额外安装步骤。

默认用户须为 `deck`，系统须为 SteamOS x86_64。安装器保留 SteamOS 只读保护，安装后台服务并重启 Decky；首次安装加速开关默认关闭，避免在还没有账号订阅时自动接管网络。已有用户的加速设置和订阅数据保留。

## 当前限制与状态

- alpha.8 的现有配置更新流程曾在 SteamOS 3.8.16 上使用；alpha.9 新增的“完全无原版数据首次启动”和“未安装 Decky 时自动部署”尚未在真实 Deck 上验证。
- 自动初始化在插件首次同步时运行，可能比后续更新慢；原版辅助组件可能短暂显示窗口。
- 订阅目前手动同步，没有定时更新。
- 默认公网流量经过所选节点、局域网直连；没有单独的国内网站或 Steam 下载直连规则。
- 请勿同时运行其他代理工具的 TUN。
- 安装器会备份旧插件和后台文件，但还不提供整个安装过程的一键事务回滚。
- 桌面模式保持后台加速；登录及订阅设置仍通过 Decky 操作。

应急停止：`sudo systemctl stop miaozi-deck.service`。

## 从源码构建（仅开发者）

Node.js 20+、npm、Python 3.10+：

```sh
npm ci
npx tsc --noEmit
npm run build
python3 scripts/package_release.py --assets-dir /path/to/runtime-assets --official-dir /path/to/official-runtime --decky-dir /path/to/decky-runtime
```

输出位于 `release/`：完整 `.run` 文件、对应 SHA-256 文件，以及打包用 ZIP。普通用户只下载 `.run` 即可。

GitHub 自动生成的 Source code ZIP 只有源码，不能直接安装。第三方二进制不放进 Git 历史，通过打包时提供的资源目录集成，详见 [第三方资源](docs/THIRD_PARTY.md)。

## 源码结构

| 文件 | 用途 |
| --- | --- |
| `src/index.tsx` | Decky 界面 |
| `main.py` | 账号、订阅及插件接口 |
| `bootstrap_profile.py` | 新用户的隔离初始化，不使用他人配置 |
| `native_subscription.py` | 内置组件同步订阅；兼容老用户本地配置 |
| `acceleration_service.py` | 独立后台加速服务 |
| `core_session.py` / `cache_nodes.py` | 内核通信与节点解析 |
| `install.sh` | 在线安装入口 |
| `scripts/` | 完整包、自解压文件及本地安装脚本 |

## 隐私与许可

不将账号密码、订阅地址、节点配置或固定加密密钥打入安装包。新用户的初始化密钥在其自己的临时目录随机生成；临时数据在同步完成后清理。见 [隐私说明](docs/PRIVACY.md)。

本项目非喵子官方项目，原创部分暂为 `UNLICENSED`。内置第三方软件各自适用其许可证；本地集成不等于已获全部公开再分发许可。公开 Release 前由发布者处理许可与源码提供义务。发布步骤见 [GitHub 发布说明](docs/PUBLISHING.md)。
