# Rejestruje zadanie Harmonogramu Windows, które co 15 minut uruchamia cykl doradcy.
# Uruchom RĘCZNIE: powershell -ExecutionPolicy Bypass -File install_task.ps1
# Zmienne OANDA_TOKEN, FRED_API_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID muszą być ustawione
# jako zmienne użytkownika (np. [Environment]::SetEnvironmentVariable("OANDA_TOKEN", "...", "User")).
param(
    [string]$Python = "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
    [string]$TaskName = "GoldAdvisorCycle"
)

$dir = $PSScriptRoot
if (-not (Test-Path $Python)) { throw "Nie znaleziono Pythona: $Python" }

# Najbliższa pełna kwarta plus 1 minuta, żeby świeca M15 była już zamknięta.
$now = Get-Date
$next = $now.Date.AddMinutes([math]::Ceiling($now.TimeOfDay.TotalMinutes / 15) * 15 + 1)
if ($next -le $now) { $next = $next.AddMinutes(15) }

$action = New-ScheduledTaskAction -Execute $Python -Argument "main.py cycle" -WorkingDirectory $dir
$trigger = New-ScheduledTaskTrigger -Once -At $next -RepetitionInterval (New-TimeSpan -Minutes 15) -RepetitionDuration (New-TimeSpan -Days 3650)
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 5)
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings `
    -Description "Doradca XAU/USD: cykl co 15 minut" -Force | Out-Null
Write-Host "Zarejestrowano zadanie '$TaskName', pierwsze uruchomienie: $next"
Write-Host "Usunięcie: Unregister-ScheduledTask -TaskName $TaskName -Confirm:`$false"
