# 喵子 Deck

在 Steam Deck 上使用喵子加速的非官方 Decky 插件。支持账号登录、订阅同步和节点管理，切换游戏模式与桌面模式后也能保持加速。

[下载安装包](https://github.com/YinYangGuaiQi/MiaoziDeck/releases) · [反馈问题](https://github.com/YinYangGuaiQi/MiaoziDeck/issues)

## 功能

- 在插件内登录账号、更新订阅。
- 一键开启或关闭加速。
- 使用 Yacd 仪表盘切换节点、测速。
- 单文件安装，自动准备所需组件；未安装 Decky 时自动补齐。

## 安装

1. 切换到桌面模式，下载 [完整安装文件](https://github.com/YinYangGuaiQi/MiaoziDeck/releases/tag/v0.1.0-alpha.9)，放入下载目录。
2. 打开 Konsole，运行：

   ```sh
   bash ~/Downloads/MiaoziDeck-0.1.0-alpha.9.sh
   ```

3. 按提示输入本机管理员密码，完成后返回游戏模式。

无需手动解压、复制配置或提前登录原版客户端。当前仓库为私有，下载时需登录有权限的 GitHub 账号。

<details>
<summary>在线安装命令（仓库公开后可用）</summary>

```sh
curl -fL --proto '=https' https://raw.githubusercontent.com/YinYangGuaiQi/MiaoziDeck/main/install.sh -o /tmp/miaozi-deck-install.sh && bash /tmp/miaozi-deck-install.sh --version v0.1.0-alpha.9
```

</details>

## 使用

打开 **… → Decky → Miaozi Deck → 设置**，登录喵子账号并同步订阅，然后开启加速。节点切换和测速在仪表盘中操作。

## 说明

- 当前为 alpha.9 测试版，全新设备的首次登录和自动安装 Decky 尚待真机验证。
- 适用于默认用户为 `deck` 的 SteamOS x86_64；请勿同时开启其他代理工具的 TUN。
- 本项目与喵子官方无隶属关系。[隐私说明](docs/PRIVACY.md) · [第三方资源](docs/THIRD_PARTY.md) · [开发与构建](docs/DEVELOPMENT.md)
