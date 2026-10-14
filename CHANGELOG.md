# 更新日志

本文件记录 NoneBot2 WebUI 面向用户的版本变更。

格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本号遵循语义化版本。

## [Unreleased]

## [1.1.1] - 2026-10-14

### 修复

- 修复关闭内置终端时可能因 PTY 会话销毁死锁导致整个面板卡死、全部接口无响应的问题
- 修复系统监控数据采集占用请求处理线程、偶发拖慢其它接口的问题
- 修复上传插件包安装依赖期间面板长时间无响应的问题

## [1.1.0] - 2026-09-09

### 新增

- 系统设置新增邮件通知，可配置 SMTP 服务器、发件账号与通知收件邮箱
- 支持发送测试邮件验证邮件配置
- 机器人 QQ 断连或进程异常退出时自动发送邮件提醒
- 可视化插件新增「发送邮件」组件

### 修复

- 修复各页面顶栏标题始终显示为「仪表盘」的问题
- 修复可视化插件组件列表左右留白不一致的问题

## [1.0.1] - 2026-08-22

### 修复

- 修复保存机器人时监听地址与端口未同步到 `.env` 的问题
- 修复可视化插件代码生成、更新流程与认证相关的安全问题

## [1.0.0] - 2026-08-19

首个正式版本。

[Unreleased]: https://github.com/HuajiMX/nonebot-webui/compare/v1.1.1...HEAD
[1.1.1]: https://github.com/HuajiMX/nonebot-webui/compare/v1.1.0...v1.1.1
[1.1.0]: https://github.com/HuajiMX/nonebot-webui/compare/v1.0.1...v1.1.0
[1.0.1]: https://github.com/HuajiMX/nonebot-webui/compare/v1.0.0...v1.0.1
[1.0.0]: https://github.com/HuajiMX/nonebot-webui/releases/tag/v1.0.0
