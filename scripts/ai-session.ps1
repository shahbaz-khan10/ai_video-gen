# Frees Docker VM memory for video generation by stopping idle, memory-heavy containers of OTHER projects,
# and starts them again afterwards. Nothing is removed: containers, volumes and data are kept.
#
#   powershell -File scripts\ai-session.ps1 free      # before long or 480p video jobs
#   powershell -File scripts\ai-session.ps1 free-all  # stop EVERY other container (ERP etc. included)
#   powershell -File scripts\ai-session.ps1 restore   # when done: starts everything this script stopped
#   powershell -File scripts\ai-session.ps1 status
#
# Why: the video backend needs ~15-18.5 GiB of the 23.5 GiB WSL VM; the other projects' containers used
# 7.9 GiB while idle (sourcebot-qdrant alone 4.1 GiB). Over the limit, the VM swaps and the GPU job stalls
# (measured 2026-11-14, docs/AI_VIDEO_STUDIO_QUALITY_ROADMAP.md section 3.7).

param([ValidateSet("free", "free-all", "restore", "status")][string]$Action = "status")

# Compose projects that are safe to stop while generating (development tools, not the ERP).
$Projects = @("sourcebot", "ai-human-clone")
$StateFile = Join-Path $PSScriptRoot ".ai-session-stopped.txt"

function Get-ProjectContainers([string]$state) {
    $filter = if ($state -eq "running") { "status=running" } else { "status=exited" }
    foreach ($p in $Projects) {
        docker ps -a --filter "label=com.docker.compose.project=$p" --filter $filter --format "{{.Names}}"
    }
}

function Show-Memory {
    $rows = docker stats --no-stream --format "{{.Name}}`t{{.MemUsage}}"
    $total = 0.0
    foreach ($r in $rows) {
        $used = ($r -split "`t")[1].Split("/")[0].Trim()
        if ($used -match "([\d.]+)(\w+)") {
            $mb = [double]$Matches[1] * @{ "B" = 1 / 1MB; "KiB" = 1 / 1024; "MiB" = 1; "GiB" = 1024 }[$Matches[2]]
            $total += $mb
        }
    }
    "{0} running containers use {1:N1} GiB" -f $rows.Count, ($total / 1024)
}

function Stop-AndRemember([string[]]$names) {
    if ($names.Count -eq 0) { "Nothing to stop."; return }
    # Append, so "free" then "free-all" still restores everything.
    $previous = if (Test-Path $StateFile) { @(Get-Content $StateFile | Where-Object { $_ }) } else { @() }
    @($previous + $names) | Select-Object -Unique | Set-Content -Encoding utf8 $StateFile
    "Stopping $($names.Count): $($names -join ', ')"
    docker stop $names | Out-Null
}

switch ($Action) {
    "free" {
        Stop-AndRemember @(Get-ProjectContainers "running")
        Show-Memory
    }
    "free-all" {
        # Everything except this app and benchmark runs.
        $names = @(docker ps --format "{{.Names}}" | Where-Object { $_ -and $_ -notmatch "^(ai_video-gen|vae-bench|bench-)" })
        Stop-AndRemember $names
        Show-Memory
    }
    "restore" {
        if (-not (Test-Path $StateFile)) { "No containers were stopped by this script."; break }
        $names = @(Get-Content $StateFile | Where-Object { $_ })
        "Starting: $($names -join ', ')"
        docker start $names | Out-Null
        Remove-Item $StateFile -Confirm:$false
        Show-Memory
    }
    "status" {
        Show-Memory
        if (Test-Path $StateFile) { "Stopped by this script: $((Get-Content $StateFile) -join ', ')" }
    }
}
