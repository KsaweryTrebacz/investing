# Aurum Invest - Uruchamianie w nowoczesnej przeglądarce
$indexPath = Join-Path $PSScriptRoot "index.html"

# Wyszukiwanie Edge lub Chrome
$browserCandidates = @(
    "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    "C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    "C:\Program Files\Google\Chrome\Application\chrome.exe",
    "C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
)

$targetBrowser = $browserCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1

if (-not $targetBrowser) {
    # Szukaj w katalogu EdgeCore
    $edgeCore = Get-ChildItem -Path "C:\Program Files (x86)\Microsoft\EdgeCore" -Filter "msedge.exe" -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($edgeCore) {
        $targetBrowser = $edgeCore.FullName
    }
}

if ($targetBrowser) {
    Write-Host "Uruchamianie Aurum Invest w: $targetBrowser" -ForegroundColor Yellow
    Start-Process $targetBrowser -ArgumentList "`"$indexPath`""
} else {
    Write-Host "Otwieranie Aurum Invest w domyślnej przeglądarce..." -ForegroundColor Yellow
    Start-Process $indexPath
}
