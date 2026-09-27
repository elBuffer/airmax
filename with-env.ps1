# Run a command with settings from this repository's ignored .env file.
# Examples:
#   .\with-env.ps1 aws sts get-caller-identity
#   .\with-env.ps1 terraform '-chdir=infra/terraform' plan '-out=dev.tfplan'

if ($args.Count -eq 0) {
    throw 'Usage: .\with-env.ps1 <command> [arguments]'
}

$command = $args[0]
$commandArgs = @($args | Select-Object -Skip 1)
$map = @{
    'access_key'            = 'AWS_ACCESS_KEY_ID'
    'secret_key'            = 'AWS_SECRET_ACCESS_KEY'
    'account'               = 'AWS_ACCOUNT_ID'
    'region'                = 'AWS_DEFAULT_REGION'
    'AWS_ACCESS_KEY_ID'     = 'AWS_ACCESS_KEY_ID'
    'AWS_SECRET_ACCESS_KEY' = 'AWS_SECRET_ACCESS_KEY'
    'AWS_SESSION_TOKEN'     = 'AWS_SESSION_TOKEN'
    'AWS_DEFAULT_REGION'    = 'AWS_DEFAULT_REGION'
    'AWS_ACCOUNT_ID'        = 'AWS_ACCOUNT_ID'
}
$names = ($map.Values | Select-Object -Unique) + 'AWS_PROFILE' + 'TF_VAR_expected_account_id'
$saved = @{}
foreach ($name in $names) {
    $saved[$name] = [Environment]::GetEnvironmentVariable($name, 'Process')
}

try {
    $env:AWS_PROFILE = $null
    foreach ($line in Get-Content (Join-Path $PSScriptRoot '.env')) {
        if ($line -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$' -and $map.ContainsKey($matches[1])) {
            $value = $matches[2].Trim().Trim('"').Trim("'")
            [Environment]::SetEnvironmentVariable($map[$matches[1]], $value, 'Process')
        }
    }
    $env:TF_VAR_expected_account_id = $env:AWS_ACCOUNT_ID
    & $command @commandArgs
    $code = $LASTEXITCODE
}
finally {
    foreach ($name in $saved.Keys) {
        [Environment]::SetEnvironmentVariable($name, $saved[$name], 'Process')
    }
}
exit $code
