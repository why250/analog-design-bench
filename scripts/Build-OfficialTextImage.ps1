#Requires -Version 7.3
<#
.SYNOPSIS
Builds an official verifier using the reusable text-stdin skill helper.
#>
[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [Parameter(Mandatory = $true)][string]$ContextDirectory,
    [Parameter(Mandatory = $true)][string]$ImageName,
    [Parameter(Mandatory = $true)][string]$DockerPath,
    [string]$ManifestPath,
    [switch]$VerifyVerifier
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path $PSScriptRoot -Parent
$localBuildScript = Join-Path $repoRoot 'skills/docker-text-stdin-build/scripts/Build-TextDockerImage.ps1'
if (-not (Test-Path -LiteralPath $localBuildScript -PathType Leaf)) {
    throw 'TextStdin requires the optional local skill. For ordinary Docker builds, omit -TextStdin.'
}
$contextPath = (Resolve-Path -LiteralPath $ContextDirectory).Path
$tasksPath = (Resolve-Path -LiteralPath (Join-Path $repoRoot 'tasks')).Path
if (-not $contextPath.StartsWith($tasksPath + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Official text build contexts must be inside this repository''s tasks directory.'
}
$items = @(Get-ChildItem -LiteralPath $contextPath -Recurse -Force)
if (@($items | Where-Object { $_.Attributes -band [IO.FileAttributes]::ReparsePoint }).Count) {
    throw 'Linked files or directories are not supported in official task contexts.'
}
$sourceFiles = @($items | Where-Object { -not $_.PSIsContainer } | ForEach-Object {
    [IO.Path]::GetRelativePath($contextPath, $_.FullName).Replace('\', '/')
})
$imageFileMap = @{}
if ($VerifyVerifier) {
    foreach ($relative in $sourceFiles) {
        if ($relative -in @('Dockerfile', '.dockerignore')) { continue }
        $imageFileMap[$relative] = if ($relative -eq 'test.sh') { '/tests/test.sh' } else { "/app/analog_arena_tests/$relative" }
    }
}
$buildArguments = @{
    ContextDirectory = $contextPath
    SourceFiles = $sourceFiles
    ImageName = $ImageName
    DockerPath = $DockerPath
    Platform = 'linux/amd64'
    ManifestPath = $ManifestPath
    ImageFileMap = $imageFileMap
    WhatIf = [bool]$WhatIfPreference
}
& $localBuildScript @buildArguments
