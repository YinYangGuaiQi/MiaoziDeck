# 完整安装包的第三方资源

二进制只进入本机完整安装文件，源码 ZIP 不包含它们或任何用户数据。

| 资源目录 | 来源 |
| --- | --- |
| `bin/FlClashCore` | 用户提供的喵子 2.0.0 AMD64 deb；版本、SHA-256 见 `vendor.json` |
| `official/` | 同一 deb 的 `/usr/share/FlClash` 原版程序、Flutter 资源与库；不包含个人配置 |
| `official/vendor/` | Ubuntu Jammy 的 Ayatana、dbusmenu、Keybinder 库；原包 URL、版本及 SHA-256 见目录内 `SOURCES.json`，版权文件在 `official/licenses/` |
| `decky/` | [Decky Loader](https://github.com/SteamDeckHomebrew/decky-loader) v3.2.9 发布二进制、服务模板和 LICENSE；仅缺少 Decky 时安装 |
| `dashboard/` | [Yacd](https://github.com/haishanh/yacd) 静态构建及许可证 |
| `certs/` | certifi 证书集合及来源、许可证文件 |
| `py_modules/` | Linux x86_64 pycryptodomex 模块及来源、许可证文件 |

打包命令的三个资源参数：

- `--assets-dir`：包含 `bin`、`dashboard`、`certs` 和 `py_modules` 的干净运行资源目录。
- `--official-dir`：包含 `FlClash`、`FlClashCore`、`lib`、`data`、`vendor` 和 `licenses` 的原版运行组件目录。
- `--decky-dir`：包含 `PluginLoader`、`plugin_loader.service.in`、`SOURCE.json` 与 `LICENSE` 的 Decky 资源目录。

初始化流程参考上游 [FlClash profiles 数据结构](https://github.com/chen08209/FlClash/blob/main/lib/database/profiles.dart)，实际数据库由内置原版程序自己创建；未知的必填字段会导致初始化明确失败，不会猜测并覆盖用户数据。

前端依赖许可证见相应项目。喵子原版组件的公开再分发授权未确认；公开完整包前需处理相关许可。Yacd、Decky 以及其他组件的许可证和源码提供义务也应各自遵守。
