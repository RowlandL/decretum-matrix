# Offline Wiki Source

此目录是 GitHub Wiki 的版本化离线权威。发布线上 Wiki 时只同步以下页面：

```text
Home.md
Installation.md
Usage.md
Governance.md
Architecture.md
Troubleshooting.md
Release-Notes.md
_Sidebar.md
```

`README.md` 与 `check-sync.ps1` 只存在于产品仓，不发布到 Wiki repo。

本地完整性检查：

```powershell
pwsh -File docs/wiki/check-sync.ps1
```

线上/线下一致性检查：

```powershell
pwsh -File docs/wiki/check-sync.ps1 -OnlineCheckout <wiki-checkout>
```

脚本只读，不 clone、copy、commit 或 push。外部创建和发布仍需独立授权。
