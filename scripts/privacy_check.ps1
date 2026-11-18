$ErrorActionPreference = "Stop"

$forbidden = @(
    ".env",
    "data/candidate_profile_input.md",
    "data/candidate_profile.json",
    "data/search_goal_input.json",
    "data/state.db",
    "data/analytics.json"
)

$tracked = @(git ls-files)
foreach ($path in $forbidden) {
    if ($tracked -contains $path) {
        throw "Privacy check failed: forbidden tracked file: $path"
    }
}

$badExtensions = @(".db", ".sqlite", ".sqlite3", ".log", ".pem", ".key", ".p12")
foreach ($path in $tracked) {
    if ($badExtensions -contains [IO.Path]::GetExtension($path).ToLowerInvariant()) {
        throw "Privacy check failed: forbidden file type: $path"
    }
}

$patterns = @(
    "sk-[A-Za-z0-9_-]{20,}",
    "-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----",
    "AKIA[0-9A-Z]{16}"
)

foreach ($pattern in $patterns) {
    $matches = @(
        git grep -n -I -E -e $pattern -- . ":(exclude)scripts/privacy_check.ps1" 2>$null
    )
    if ($matches.Count -gt 0) {
        throw "Privacy check failed: possible credential pattern: $pattern"
    }
}

Write-Host "Privacy check passed: no runtime data or common credential patterns tracked."

