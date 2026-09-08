param(
  [Parameter(ValueFromRemainingArguments = $true)]
  [string[]]$Args
)

if ($Args.Count -eq 1 -and $Args[0] -eq "install-command") {
  $profilePath = if ($env:CLEAR_POWERSHELL_PROFILE) {
    $env:CLEAR_POWERSHELL_PROFILE
  } else {
    $PROFILE.CurrentUserCurrentHost
  }
  $profileDir = Split-Path -Parent $profilePath
  $launcherPath = Join-Path $PSScriptRoot "clear.ps1"
  $escapedLauncherPath = $launcherPath.Replace("'", "''")
  $markerStart = "# >>> Clear launcher >>>"
  $markerEnd = "# <<< Clear launcher <<<"
  $block = @"
$markerStart
Remove-Item Alias:clear -Force -ErrorAction SilentlyContinue
function global:clear {
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
  $pattern = "(?s)\r?\n?" + [regex]::Escape($markerStart) + ".*?" + [regex]::Escape($markerEnd) + "\r?\n?"
  $withoutOldBlock = [regex]::Replace($existing, $pattern, "").TrimEnd()
  $newProfile = if ($withoutOldBlock) {
    $withoutOldBlock + [Environment]::NewLine + [Environment]::NewLine + $block + [Environment]::NewLine
  } else {
    $block + [Environment]::NewLine
  }
  Set-Content -LiteralPath $profilePath -Value $newProfile -Encoding utf8

  Remove-Item Alias:clear -Force -ErrorAction SilentlyContinue
  $launcherFunction = [scriptblock]::Create("& '$escapedLauncherPath' @args")
  Set-Item -Path Function:\global:clear -Value $launcherFunction

  Write-Output ">> Installed the Clear launcher in $profilePath"
  Write-Output ">> Run 'clear' to start. Use 'Clear-Host' or 'cls' to clear the terminal."
  return
}

python "$PSScriptRoot\clear_bootstrap.py" @Args
