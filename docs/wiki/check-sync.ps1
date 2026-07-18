[CmdletBinding()]
param(
    [string]$OnlineCheckout
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$pageNames = @(
    "Home.md",
    "Installation.md",
    "Usage.md",
    "Governance.md",
    "Architecture.md",
    "Troubleshooting.md",
    "Release-Notes.md",
    "_Sidebar.md"
)

function Get-PageInventory([string]$Root) {
    $resolved = (Resolve-Path -LiteralPath $Root).Path
    $items = foreach ($name in $pageNames) {
        $path = Join-Path $resolved $name
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
            throw "wiki page missing: $name"
        }
        if ((Get-Item -LiteralPath $path).Length -eq 0) {
            throw "wiki page empty: $name"
        }
        [ordered]@{
            path = $name
            sha256 = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()
        }
    }
    return @($items)
}

$local = Get-PageInventory $PSScriptRoot
$result = [ordered]@{
    schema = "decretum.wiki_sync_check.v1"
    status = "LOCAL_COMPLETE"
    page_count = $local.Count
    local_pages = $local
    online_checkout = $null
    consistent = $null
}

if ($OnlineCheckout) {
    $onlineRoot = (Resolve-Path -LiteralPath $OnlineCheckout).Path
    $online = Get-PageInventory $onlineRoot
    $extra = @(Get-ChildItem -LiteralPath $onlineRoot -File -Filter "*.md" |
        Where-Object { $_.Name -notin $pageNames } |
        ForEach-Object Name)
    $consistent = ($extra.Count -eq 0)
    for ($index = 0; $index -lt $local.Count; $index++) {
        $consistent = $consistent -and
            ($local[$index].path -eq $online[$index].path) -and
            ($local[$index].sha256 -eq $online[$index].sha256)
    }
    $result.status = if ($consistent) { "ONLINE_OFFLINE_CONSISTENT" } else { "MISMATCH" }
    $result.online_checkout = $onlineRoot
    $result.consistent = $consistent
}

$result | ConvertTo-Json -Depth 5
if ($result.status -eq "MISMATCH") {
    exit 2
}
