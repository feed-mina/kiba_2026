param(
  [string]$Repo = "feed-mina/kiba_2026"
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

$Gh = Resolve-Gh

$labels = @(
  @{ Name = "type/task"; Color = "0e8a16"; Description = "Executable work item" },
  @{ Name = "type/idea"; Color = "5319e7"; Description = "Idea, hypothesis, or rough note" },
  @{ Name = "type/bug"; Color = "d73a4a"; Description = "Bug or defect" },
  @{ Name = "type/doc"; Color = "0075ca"; Description = "Documentation work" },
  @{ Name = "type/decision"; Color = "fbca04"; Description = "Decision needed or decision record" },
  @{ Name = "loop/daily"; Color = "bfdadc"; Description = "Daily loop" },
  @{ Name = "loop/issue"; Color = "c2e0c6"; Description = "Issue-level loop" },
  @{ Name = "loop/publish"; Color = "fef2c0"; Description = "Quartz publishing loop" },
  @{ Name = "public/candidate"; Color = "f9d0c4"; Description = "Candidate for public Quartz page" },
  @{ Name = "public/published"; Color = "b4a7d6"; Description = "Published to public Quartz page" },
  @{ Name = "needs/clarify"; Color = "d4c5f9"; Description = "Needs purpose or done criteria" },
  @{ Name = "needs/reflect"; Color = "fef2c0"; Description = "Needs reflection before close" }
)

foreach ($label in $labels) {
  & $Gh label create $label.Name `
    -R $Repo `
    --color $label.Color `
    --description $label.Description `
    --force
}

Write-Host "Loop labels are ready for $Repo."
