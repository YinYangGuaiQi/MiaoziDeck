# 配置和隐私

不要向 GitHub 提交：账号密码、认证令牌、订阅 URL、节点配置、仪表盘完整认证 URL、SSH 私钥、原版客户端数据或未经检查的诊断日志。

本插件运行时使用的敏感数据主要位于：

- `/home/deck/homebrew/data/MiaoziDeck/`
- `/var/lib/miaozi-deck/state/`
- 原版客户端的 `/home/deck/.local/share/com.follow.clash/`

源码包不包含以上目录。账号密码不持久化；账号会话保存在内存中，订阅地址与节点配置会保存在本机，因此仍应当视为敏感信息。

源码中的官方服务引导 URL、公开连通性测试地址、DNS 地址和 `vendor.json` 中的内核校验值不是个人凭据，保留它们用于正常运行和完整性校验。

`.gitignore` 只是辅助措施，不会自动移除已被 Git 跟踪的敏感文件。公开问题反馈时请仅提交必要的错误信息并检查内容。
