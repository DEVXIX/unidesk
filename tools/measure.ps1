# Measure unidesk's memory and CPU for a set of widget layouts, hidden off-screen.
#   powershell -File tools\measure.ps1 [-Only name]
param([string]$Only = "", [string]$Backend = "")

$root = Split-Path $PSScriptRoot -Parent
$defaults = Get-Content "$root\unidesk\defaults\config.yaml" -Raw
$head = $defaults.Substring(0, $defaults.IndexOf("widgets:"))
$blocks = @{}
foreach ($m in [regex]::Matches($defaults, '(?ms)^  - id: (\S+)\r?\n.*?(?=^  - id: |^  #|\z)')) { $blocks[$m.Groups[1].Value] = $m.Value }

$cases = [ordered]@{
    "empty"   = @()
    "time"    = @("time")
    "clock"   = @("clock")
    "card"    = @("music")
    "poster"  = @("music-poster")
    "tiles"   = @("cpu", "ram", "gpu", "weather", "calendar")
    "profile" = @("profile")
    "github"  = @("github")
    "all"     = @($blocks.Keys)
}

foreach ($name in $cases.Keys) {
    if ($Only -and $name -ne $Only) { continue }
    $home_ = Join-Path $env:TEMP "unidesk-measure-$name"
    New-Item -ItemType Directory -Force $home_ | Out-Null
    $body = ($cases[$name] | ForEach-Object { $blocks[$_] }) -join ""
    Set-Content "$home_\config.yaml" ($head + "widgets:`n" + $body) -Encoding utf8

    $env:UNIDESK_HOME = $home_
    $env:UNIDESK_SNAPSHOT = "$home_\shot.png"
    $env:UNIDESK_SNAPSHOT_DELAY = "45000"
    if ($Backend) { $env:QSG_RHI_BACKEND = $Backend }
    $p = Start-Process pythonw -ArgumentList "-m unidesk" -WorkingDirectory $root -PassThru
    Start-Sleep 18
    $c1 = (Get-Process -Id $p.Id).TotalProcessorTime
    Start-Sleep 20
    $pr = Get-Process -Id $p.Id
    $cpu = (($pr.TotalProcessorTime - $c1).TotalMilliseconds / 20000) * 100 / [Environment]::ProcessorCount
    "{0,-8} private {1,4:N0} MB   working set {2,4:N0} MB   cpu {3:N2}%" -f $name, ($pr.PrivateMemorySize64 / 1MB), ($pr.WorkingSet64 / 1MB), $cpu
    Stop-Process -Id $p.Id -ErrorAction SilentlyContinue
    Get-CimInstance Win32_Process -Filter "Name='media-bridge.exe'" | ForEach-Object { Stop-Process -Id $_.ProcessId -ErrorAction SilentlyContinue }
}
Remove-Item Env:UNIDESK_HOME, Env:UNIDESK_SNAPSHOT, Env:UNIDESK_SNAPSHOT_DELAY -ErrorAction SilentlyContinue
