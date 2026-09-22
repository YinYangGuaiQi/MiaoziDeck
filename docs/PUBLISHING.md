# alpha.9 发布说明

仓库：[YinYangGuaiQi/MiaoziDeck](https://github.com/YinYangGuaiQi/MiaoziDeck)，保持私有。About 简介：

> Steam Deck 喵子加速非官方 Decky 插件：一键完整安装、账号登录、订阅同步、跨模式后台加速与 Yacd 节点管理。

## 公开发布前仍待完成

1. 完成真机验证：双击 `.desktop` 安装文件后可完成安装，新用户没有原版客户端、没有原版配置时，可以在插件内首次登录、同步和开启加速。
2. 验证新装 Decky 分支及已有 Decky 升级分支。
3. 确定原创代码和第三方组件的分发许可；目前包内原版组件的公开再分发授权未确认。

当前作为私有仓库中的普通 Release 发布并设为 Latest，便于下载。版本仍为 alpha 测试版，尚未完成全新 Steam Deck 真机验证；Latest 不代表稳定性认证。

## 上传

将源码目录内容作为 GitHub 仓库根目录，默认分支 `main`。不提交二进制、运行配置、`node_modules` 或 `release`。

使用标签 `v0.1.0-alpha.9`，发布普通 Release 并设为 Latest，上传：

- `MiaoziDeck-0.1.0-alpha.9.desktop`：推荐用户下载并双击的完整安装文件。
- `MiaoziDeck-0.1.0-alpha.9.desktop.sha256`：可选的额外校验文件。
- `MiaoziDeck-0.1.0-alpha.9.sh`：供在线入口和命令行安装使用。
- `MiaoziDeck-0.1.0-alpha.9.sh.sha256`：在线入口自动下载的校验文件。

用户只需下载第一个文件，文件内已包含全部资源和校验信息。从任意文件夹双击，确认系统的运行提示并输入管理员密码即可进入安装流程，不要求填写路径或打开终端粘贴命令。不要把 Source code ZIP 标为安装包。

README 已填写实际仓库地址。私有状态下用户通过已登录的 GitHub 下载单文件；公开状态下才能直接使用匿名 curl 命令。不要为了启用 curl 自动更改仓库可见性。

## Release 描述

alpha.9 将原版订阅组件、必要 Linux 运行库、加速内核、Yacd 仪表盘和 Decky 安装资源合并为单个 `.desktop` 完整安装文件。用户双击运行后在本机输入管理员密码即可开始部署，账号只需在插件内登录。

已有 Decky 保留；已有订阅和加速设置保留。新安装默认关闭加速，登录后可开启。新用户由内置组件自动建立隔离订阅配置，不再要求先手动登录官方客户端。

本版本仍处于测试阶段，双击入口、全新环境的首次登录初始化和自动 Decky 安装待真机验证。请勿将源码检查通过描述成设备端测试通过。
