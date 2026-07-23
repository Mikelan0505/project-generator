[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [string]$Project
)

$ErrorActionPreference = "Stop"

$repositoryRoot = $PSScriptRoot
$scriptPath = Join-Path -Path $repositoryRoot -ChildPath "script.py"
$outputsPath = Join-Path -Path $repositoryRoot -ChildPath "outputs"

$pythonCommand = Get-Command `
    -Name "python" `
    -CommandType Application `
    -ErrorAction SilentlyContinue |
    Select-Object -First 1

if ($null -eq $pythonCommand) {
    throw (
        "Python command 'python' was not found in PATH. " +
        "Install Python, then run .\sync-dist.ps1 <project-name>."
    )
}

if (-not (Test-Path -LiteralPath $scriptPath -PathType Leaf)) {
    throw "script.py was not found: $scriptPath"
}

$pythonPath = $pythonCommand.Source

function Test-GeneratedProjectName {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name
    )

    $validationCode = @"
import sys
sys.path.insert(0, sys.argv[1])
from project_naming import sanitize_project_slug
try:
    is_valid = sanitize_project_slug(sys.argv[2]) == sys.argv[2]
except ValueError:
    is_valid = False
raise SystemExit(0 if is_valid else 2)
"@

    & $pythonPath `
        -B `
        -c $validationCode `
        $repositoryRoot `
        $Name

    $validationExitCode = $LASTEXITCODE

    if ($validationExitCode -eq 0) {
        return $true
    }

    if ($validationExitCode -eq 2) {
        return $false
    }

    throw (
        "Project name validation failed with exit code " +
        "$validationExitCode."
    )
}

if ($PSBoundParameters.ContainsKey("Project")) {
    $selectedProject = $Project
}
else {
    $candidateProjects = @()

    if (Test-Path -LiteralPath $outputsPath -PathType Container) {
        $excludedAttributes = (
            [System.IO.FileAttributes]::Hidden -bor
            [System.IO.FileAttributes]::System
        )

        foreach (
            $directory in Get-ChildItem `
                -LiteralPath $outputsPath `
                -Directory `
                -Force
        ) {
            $isDotDirectory = (
                $directory.Name.StartsWith(
                    ".",
                    [System.StringComparison]::Ordinal
                )
            )
            $hasExcludedAttributes = (
                (
                    $directory.Attributes -band
                    $excludedAttributes
                ) -ne 0
            )

            if ($isDotDirectory -or $hasExcludedAttributes) {
                continue
            }

            if (Test-GeneratedProjectName -Name $directory.Name) {
                $candidateProjects += $directory.Name
            }
        }
    }

    $candidateProjects = @(
        $candidateProjects |
        Sort-Object
    )

    if ($candidateProjects.Count -eq 0) {
        throw (
            "No updateable projects were found in outputs. " +
            "Generate a project first. Usage: " +
            ".\sync-dist.ps1 <project-name>"
        )
    }

    if ($candidateProjects.Count -gt 1) {
        Write-Host (
            "Multiple projects exist; " +
            "a project cannot be auto-selected."
        )
        Write-Host "Available projects:"

        foreach ($candidateProject in $candidateProjects) {
            Write-Host "- $candidateProject"
        }

        Write-Host (
            "Specify one explicitly: " +
            ".\sync-dist.ps1 <project-name>"
        )
        throw (
            "A project name is required when multiple projects exist."
        )
    }

    $selectedProject = $candidateProjects[0]
    Write-Host "Auto-selected project: $selectedProject"
}

Write-Host "Selected project: $selectedProject"
Write-Host (
    "Delegating the dist update to the existing script.py " +
    "--refresh-dist implementation."
)

& $pythonPath `
    $scriptPath `
    "--refresh-dist" `
    "--project" `
    $selectedProject

$scriptExitCode = $LASTEXITCODE

if ($scriptExitCode -ne 0) {
    throw (
        "Dist update failed for '$selectedProject' " +
        "with exit code $scriptExitCode."
    )
}

Write-Host "Dist update completed: $selectedProject"
