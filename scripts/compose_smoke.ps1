param(
    [string]$ComposeFile = "docker-compose.yml",
    [int]$TimeoutSeconds = 240,
    [switch]$SkipBuild
)

$ErrorActionPreference = "Stop"

function Write-Step {
    param([string]$Message)
    Write-Host "==> $Message"
}

function Invoke-Compose {
    param([string[]]$Arguments)
    $previousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $output = & docker compose -f $ComposeFile --profile gateway @Arguments 2>&1
    } finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }
    if ($LASTEXITCODE -ne 0) {
        $text = ($output | Out-String).Trim()
        if ($text -match "127\.0\.0\.1:7890|proxyconnect|registry-1\.docker\.io|Cannot connect to the Docker daemon") {
            throw "Docker compose failed before smoke checks could run. Check Docker Desktop and proxy settings. Raw error: $text"
        }
        throw "docker compose failed: $text"
    }
    return $output
}

function Wait-ContainerState {
    param(
        [string]$Name,
        [string]$Expected
    )
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    $lastStatus = ""
    while ((Get-Date) -lt $deadline) {
        $status = (& docker inspect --format "{{.State.Status}} {{if .State.Health}}{{.State.Health.Status}}{{end}} {{.State.ExitCode}}" $Name 2>$null)
        $lastStatus = "$status"
        if ($LASTEXITCODE -eq 0) {
            $parts = "$status".Trim().Split(" ", [System.StringSplitOptions]::RemoveEmptyEntries)
            $state = if ($parts.Length -ge 1) { $parts[0] } else { "" }
            $health = if ($parts.Length -ge 2) { $parts[1] } else { "" }
            $exitCode = if ($parts.Length -ge 3) { $parts[2] } else { "" }

            if ($Expected -eq "completed" -and $state -eq "exited" -and $exitCode -eq "0") {
                return
            }
            if ($Expected -eq "healthy" -and $state -eq "running" -and ($health -eq "healthy" -or $health -eq "")) {
                return
            }
        }
        Start-Sleep -Seconds 3
    }
    throw "Timed out waiting for $Name to become $Expected. Last state: $lastStatus"
}

function Invoke-HttpCheck {
    param(
        [string]$Name,
        [string]$Url,
        [string]$Contains = ""
    )
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    $lastError = $null
    while ((Get-Date) -lt $deadline) {
        try {
            $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 5
            if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 500) {
                if ($Contains -and ($response.Content -notmatch [regex]::Escape($Contains))) {
                    throw "$Name response did not contain '$Contains'"
                }
                return
            }
            $lastError = "$Name returned HTTP $($response.StatusCode)"
        } catch {
            $lastError = $_.Exception.Message
        }
        Start-Sleep -Seconds 3
    }
    throw "Timed out waiting for $Name at $Url. Last error: $lastError"
}

try {
    if (-not $env:ENVIRONMENT) {
        $env:ENVIRONMENT = "dev"
    }
    if (-not $env:AGENT_DECISION_PROVIDER) {
        $env:AGENT_DECISION_PROVIDER = "deterministic"
    }
    if (-not $env:SMARTSRE_API_KEY) {
        $env:SMARTSRE_API_KEY = $env:APP_API_KEY
    }

    Write-Step "Validating compose configuration"
    Invoke-Compose -Arguments @("config", "--quiet") | Out-Null

    Write-Step "Starting compose services"
    $upArgs = @("up", "-d", "minio-app", "migrate", "backend", "worker", "frontend", "caddy")
    if (-not $SkipBuild) {
        $upArgs = @("up", "-d", "--build", "minio-app", "migrate", "backend", "worker", "frontend", "caddy")
    }
    Invoke-Compose -Arguments $upArgs | Out-Null

    Write-Step "Waiting for infrastructure"
    Wait-ContainerState "smartsre-postgres" "healthy"
    Wait-ContainerState "smartsre-redis" "healthy"
    Wait-ContainerState "smartsre-minio" "healthy"
    Wait-ContainerState "smartsre-migrate" "completed"

    Write-Step "Waiting for application services"
    Wait-ContainerState "smartsre-backend" "healthy"
    Wait-ContainerState "smartsre-worker" "healthy"
    Wait-ContainerState "smartsre-frontend" "healthy"
    Wait-ContainerState "smartsre-caddy" "healthy"

    Write-Step "Checking backend, metrics, frontend, and gateway"
    Invoke-HttpCheck "backend live health" "http://localhost:9900/health/live" "alive"
    Invoke-HttpCheck "backend metrics" "http://localhost:9900/metrics" "smartsre_http_requests_total"
    Invoke-HttpCheck "frontend" "http://localhost:3000"
    Invoke-HttpCheck "caddy gateway health" "http://localhost/health" "status"

    Write-Step "Compose smoke passed"
} catch {
    Write-Host "ERROR: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
