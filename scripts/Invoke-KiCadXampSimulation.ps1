[CmdletBinding()]
param(
    [ValidateSet('Run', 'Export', 'Configure')]
    [string]$Mode = 'Run',
    [string]$WorkspaceDirectory,
    [string]$KiCadCliPath,
    [string]$PythonPath,
    [string]$ContainerName = 'analog-design-bench-dev'
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path $PSScriptRoot -Parent
if (-not $WorkspaceDirectory) { $WorkspaceDirectory = Join-Path $repoRoot 'workspaces/nmos-ldo' }
$workspacePath = (Resolve-Path -LiteralPath $WorkspaceDirectory).Path

if (-not $KiCadCliPath) {
    $command = Get-Command kicad-cli.exe -ErrorAction SilentlyContinue
    if ($command) { $KiCadCliPath = $command.Source }
    else {
        $KiCadCliPath = @(
            (Join-Path $env:LOCALAPPDATA 'Programs/KiCad/10.0/bin/kicad-cli.exe'),
            (Join-Path $env:ProgramFiles 'KiCad/10.0/bin/kicad-cli.exe')
        ) | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
    }
}
if (-not $KiCadCliPath -or -not (Test-Path -LiteralPath $KiCadCliPath)) {
    throw 'KiCad CLI not found. Install KiCad 10 or pass -KiCadCliPath.'
}
if (-not $PythonPath) {
    $command = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($command) { $PythonPath = $command.Source }
    else { $PythonPath = Join-Path (Split-Path $KiCadCliPath -Parent) 'python.exe' }
}
if (-not (Test-Path -LiteralPath $PythonPath)) {
    throw 'Python not found. Pass -PythonPath with a Python 3 interpreter.'
}

$engineMode = if ($Mode -eq 'Configure') { 'configure' } else { 'export' }
$exportDirectory = & $PythonPath (Join-Path $PSScriptRoot 'kicad_xamp.py') $engineMode `
    --workspace $workspacePath --kicad-cli $KiCadCliPath
if ($LASTEXITCODE -ne 0) { throw "KiCad XAMP $engineMode failed." }
$exportDirectory = [string]$exportDirectory
Write-Host "KiCad XAMP artifacts: $exportDirectory"

if ($Mode -eq 'Run') {
    # Reuse the shared container lifecycle, mount validation, and nominal bench.
    $simulationDirectory = Join-Path $exportDirectory 'simulation'
    & (Join-Path $PSScriptRoot 'Invoke-LocalSimulation.ps1') -Mode Run `
        -WorkspaceDirectory $workspacePath -ContainerName $ContainerName `
        -Circuit (Join-Path $exportDirectory 'circuit.spi') `
        -Bench (Join-Path $exportDirectory 'bench-source.spi') `
        -OutputDirectory $simulationDirectory
    Write-Host "Nominal hybrid simulation: $simulationDirectory"
    Write-Host 'Scope: schematic XAMP plus source-netlist LDO core; not official verification.'
}
