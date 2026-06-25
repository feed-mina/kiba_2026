param(
  [int]$ProjectNumber = 3,
  [string]$Owner = "feed-mina"
)

$ErrorActionPreference = "Stop"

function Resolve-Gh {
  $cmd = Get-Command gh -ErrorAction SilentlyContinue
  if ($cmd) {
    return $cmd.Source
  }

  $workspaceRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
  $portable = Get-ChildItem -Path (Join-Path $workspaceRoot ".tools") -Recurse -Filter gh.exe -ErrorAction SilentlyContinue |
    Sort-Object FullName -Descending |
    Select-Object -First 1 -ExpandProperty FullName

  if ($portable) {
    return $portable
  }

  throw "GitHub CLI (gh) is not installed. Run scripts\install_gh_portable.ps1 first."
}

function Get-ProjectFields {
  param([string]$Gh, [int]$Number, [string]$ProjectOwner)

  $json = & $Gh project field-list $Number --owner $ProjectOwner --limit 100 --format json
  if (-not $json) {
    return @()
  }

  $parsed = $json | ConvertFrom-Json
  if ($parsed.fields) {
    return @($parsed.fields)
  }
  return @()
}

function Ensure-Field {
  param(
    [string]$Gh,
    [int]$Number,
    [string]$ProjectOwner,
    [array]$Existing,
    [string]$Name,
    [string]$DataType,
    [string[]]$Options = @()
  )

  if ($Existing.name -contains $Name) {
    Write-Host "Exists: $Name"
    return
  }

  $args = @("project", "field-create", "$Number", "--owner", $ProjectOwner, "--name", $Name, "--data-type", $DataType)
  if ($DataType -eq "SINGLE_SELECT" -and $Options.Count -gt 0) {
    $args += @("--single-select-options", ($Options -join ","))
  }

  Write-Host "Creating: $Name"
  & $Gh @args
}

$Gh = Resolve-Gh
& $Gh project view $ProjectNumber --owner $Owner | Out-Host

$fields = Get-ProjectFields -Gh $Gh -Number $ProjectNumber -ProjectOwner $Owner

Ensure-Field -Gh $Gh -Number $ProjectNumber -ProjectOwner $Owner -Existing $fields -Name "Loop Type" -DataType "SINGLE_SELECT" -Options @("daily", "issue", "publish", "decision", "automation")
Ensure-Field -Gh $Gh -Number $ProjectNumber -ProjectOwner $Owner -Existing $fields -Name "Priority" -DataType "SINGLE_SELECT" -Options @("P0", "P1", "P2", "Later")
Ensure-Field -Gh $Gh -Number $ProjectNumber -ProjectOwner $Owner -Existing $fields -Name "Cycle" -DataType "TEXT"
Ensure-Field -Gh $Gh -Number $ProjectNumber -ProjectOwner $Owner -Existing $fields -Name "Obsidian Note" -DataType "TEXT"
Ensure-Field -Gh $Gh -Number $ProjectNumber -ProjectOwner $Owner -Existing $fields -Name "Public" -DataType "SINGLE_SELECT" -Options @("private", "candidate", "published")
Ensure-Field -Gh $Gh -Number $ProjectNumber -ProjectOwner $Owner -Existing $fields -Name "Quartz URL" -DataType "TEXT"
Ensure-Field -Gh $Gh -Number $ProjectNumber -ProjectOwner $Owner -Existing $fields -Name "Next Action" -DataType "TEXT"

Write-Host ""
Write-Host "Project fields are ready. If the built-in Status field already exists, align its options manually:"
Write-Host "Inbox, Clarify, Ready, Doing, Review / Reflect, Publish Candidate, Done"
