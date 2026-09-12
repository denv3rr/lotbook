param(
  [Parameter(ValueFromRemainingArguments = $true)]
  [string[]]$Args
)

python "$PSScriptRoot\lotbookctl.py" @Args
