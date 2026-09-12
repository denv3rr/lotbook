param(
  [Parameter(ValueFromRemainingArguments = $true)]
  [string[]]$Args
)

if ($Args.Count -eq 1 -and $Args[0] -eq "install-command") {
  $profilePath = if ($env:LOTBOOK_POWERSHELL_PROFILE) {
    $env:LOTBOOK_POWERSHELL_PROFILE
  } else {
    $PROFILE.CurrentUserCurrentHost
  }
  $profileDir = Split-Path -Parent $profilePath
  $launcherPath = Join-Path $PSScriptRoot "lotbook.ps1"
  $escapedLauncherPath = $launcherPath.Replace("'", "''")
  $markerStart = "# >>> Lotbook launcher >>>"
  $markerEnd = "# <<< Lotbook launcher <<<"
  $legacyStart = "# >>> Clear launcher >>>"
  $legacyEnd = "# <<< Clear launcher <<<"
  $block = @"
$markerStart
function global:lotbook {
  & '$escapedLauncherPath' @args
}
$markerEnd
"@

  if (-not (Test-Path -LiteralPath $profileDir)) {
    New-Item -ItemType Directory -Path $profileDir -Force | Out-Null
  }
  $existing = if (Test-Path -LiteralPath $profilePath) {
    Get-Content -LiteralPath $profilePath -Raw
  } else {
    ""
  }
  foreach ($pair in @(@($markerStart, $markerEnd), @($legacyStart, $legacyEnd))) {
    $pattern = "(?s)\r?\n?" + [regex]::Escape($pair[0]) + ".*?" + [regex]::Escape($pair[1]) + "\r?\n?"
    $existing = [regex]::Replace($existing, $pattern, "")
  }
  $withoutOldBlock = $existing.TrimEnd()
  $newProfile = if ($withoutOldBlock) {
    $withoutOldBlock + [Environment]::NewLine + [Environment]::NewLine + $block + [Environment]::NewLine
  } else {
    $block + [Environment]::NewLine
  }
  Set-Content -LiteralPath $profilePath -Value $newProfile -Encoding utf8

  Remove-Item Function:\global:clear -Force -ErrorAction SilentlyContinue
  $launcherFunction = [scriptblock]::Create("& '$escapedLauncherPath' @args")
  Set-Item -Path Function:\global:lotbook -Value $launcherFunction

  Write-Output ">> Installed the Lotbook launcher in $profilePath"
  Write-Output ">> Run 'lotbook' to start. The terminal 'clear' command is unchanged."
  return
}

python "$PSScriptRoot\lotbook_bootstrap.py" @Args
