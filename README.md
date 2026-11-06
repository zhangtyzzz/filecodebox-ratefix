# FileCodeBox 限流修复维护镜像

在官方 `lanol/filecodebox:latest` 基础上保留已验证的滑动窗口限流修复，供自己的 Portainer 更新。它不是上游官方发行版。

```yaml
services:
  filecodebox:
    image: ghcr.io/zhangtyzzz/filecodebox-ratefix:latest
    # 保留现有 volumes、networks、environment 和端口设置。
```

在原 Stack 中只替换 `image` 行。以后在 Portainer 更新 Stack 时选择重新拉取镜像，再部署；单纯 Restart 不会拉取更新。首次发布后需将 GHCR 包设为 Public，或在 Portainer 配置有权读取该包的 GHCR 登录信息。

## 更新机制

- 推送 `main`、手动运行 Actions，或每天一次检查上游 `latest`。
- 同一上游镜像摘要、同一维护提交已发布时跳过重建。每次需要构建时先解析上游摘要，两架构使用相同输入；部署配置始终是自有 `latest`。
- Linux amd64 和 arm64 在各自原生 runner 构建，各运行 15 项现有回归测试和空数据、无网络、无公开端口的 HTTP 启动检查。
- 两架构全部成功后才推送已测镜像，不在发布阶段重新构建；校验镜像归档、配置 ID 与双架构清单后，最后更新 `latest`。任何构建、测试或清单校验失败都不会提前覆盖原 `latest`。
- 发布作业才有 `packages: write`；预检只读源码和已有包，不需要额外 PAT。不使用生产数据、数据库、网盘凭据或 VPS 密码。

GitHub Actions 的计划任务可能延迟，也可能因平台策略或仓库长期无活动而停用。请保留工作流失败通知；Actions 红灯意味着需要处理，不等于 VPS 已经更新。

## 防止维护补丁覆盖上游修复

此仓库暂以整份 `apps/base/dependencies.py` 的**精确上游哈希**为门槛。若上游修改这个模块，构建在复制替换文件前就失败，提示 `UPSTREAM_MODULE_CHANGED`，保留已发布镜像。不能为了让 CI 变绿而直接将新哈希加入白名单。

处理步骤：比较上游新模块与 `dependencies.py`，保留上游新增行为及安全修复，只适配仍需要的限流修改；更新测试与 `upstream-policy.json`，再运行完整工作流。若上游已经修复同一问题，应验证后移除本补丁，而不是继续覆盖它。

修复保留：每个上传事件分别过期、默认 10,000 个来源 IP 容量限制、原可信代理链解析，以及运行时修改限流分钟/次数的行为。它不扩大用户配置的上传额度，也不关闭限流。

## 验证边界

15 项用例覆盖过期边界、低频事件不累计、不同 IP、容量淘汰和可信代理。另有独立门槛测试验证未知上游变化会被拒绝。HTTP 检查只验证新装启动、首页及健康接口，不包含全部 UI、生产数据库迁移、真实文件上传、S3、领取次数或所有多进程竞争场景。应用升级前仍应保留自己的数据备份并查看上游不兼容说明。

这是应用补丁维护镜像，不是整机或镜像零漏洞保证。基础 OS/Python 依赖是否更新由上游镜像决定；自动化只能跟随通过这些检查的上游更新，不能替上游修好全部安全问题。

## 源码与许可

上游是 [vastsa/FileCodeBox](https://github.com/vastsa/FileCodeBox)，实际许可为 **LGPL-3.0**，不是 MIT。保留原 `LICENSE`，补充其引用的 GPL-3.0 原文及修改说明。首次审阅基线为 [8d3e4ad904c289c1852f08c3424ae370642c58c3](https://github.com/vastsa/FileCodeBox/tree/8d3e4ad904c289c1852f08c3424ae370642c58c3)。

每次构建保存上游镜像标签记录的应用及两份前端源码提交，对应源码归档、SHA256 和本补丁随镜像放在 `/usr/share/doc/filecodebox-ratefix/`。OCI 标签记录上游输入摘要和维护提交，发布时保留 `build-<run>-<attempt>` 镜像以便定位和回退；运行用户仍使用 `latest`。

初次部署需要等待完整 Actions 成功，核对 GHCR 中存在 amd64/arm64 平台，再将现有服务切换到上面的引用。没有自动升级或删除任何 VPS 数据的 GitHub 工作流。
