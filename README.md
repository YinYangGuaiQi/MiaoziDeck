# 喵子 Deck

在 Steam Deck 上使用喵子加速的非官方 Decky 插件。支持账号登录、订阅同步和节点管理，切换游戏模式与桌面模式后也能保持加速。

[下载安装包](https://github.com/YinYangGuaiQi/MiaoziDeck/releases/latest) · [喵子官网](https://www.mzkxz-invite.us/) · [反馈问题](https://github.com/YinYangGuaiQi/MiaoziDeck/issues)

## 功能

- 在插件内登录账号、更新订阅。
- 一键开启或关闭加速。
- 使用 Yacd 仪表盘切换节点、测速。
- 单文件安装，自动准备所需组件；未安装 Decky 时自动补齐。

## 安装

1. 切换到桌面模式，前往 [最新版本](https://github.com/YinYangGuaiQi/MiaoziDeck/releases/latest)，下载其中的 `.desktop` 安装文件。
2. 在文件管理器中双击安装文件；若系统询问是否信任或允许执行，确认运行。
3. 在自动打开的安装窗口中输入本机管理员密码，完成后返回游戏模式。

只需这一个文件，保存在哪个文件夹都可以。无需手动输入命令、解压、复制配置或提前登录原版客户端。

完整组件自动安装到 `/home/deck/homebrew/plugins/MiaoziDeck`，旧版本备份也保存在 `/home/deck`。系统分区仅保留后台加速必需的文件；安装前会检查可用空间。

若浏览器将文件保存为 `.desktop.download`，请去掉末尾的 `.download` 再双击。

### 在线安装命令

```sh
curl -fsSL https://yinyangguaiqi.github.io/MiaoziDeck/i | bash
```

默认安装 Latest 版本；修改 Release 显示名称不会影响安装。需要固定版本时，将命令末尾的 `bash` 改为 `bash -s -- --version v0.1.0-alpha.9`。

## 使用

打开 **… → Decky → Miaozi Deck → 设置**，登录喵子账号并同步订阅，然后开启加速。节点切换和测速在仪表盘中操作。

## 说明

- 当前为 alpha.9 测试版，双击安装入口、全新设备的首次登录和自动安装 Decky 尚待真机验证。
- 适用于默认用户为 `deck` 的 SteamOS x86_64；请勿同时开启其他代理工具的 TUN。
- 本项目与喵子官方无隶属关系。[隐私说明](docs/PRIVACY.md) · [第三方资源](docs/THIRD_PARTY.md) · [开发与构建](docs/DEVELOPMENT.md)
