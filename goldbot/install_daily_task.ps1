# Rejestruje dwa zadania Harmonogramu Windows:
#   GoldAdvisorDaily  - cykl dzienny (main.py daily) we wtorek-sobotę o 01:30 czasu lokalnego (czyli po sesjach pon-pt)
#                       (sesja złota zamknięta po 23:00 UTC; o 01:30 PL jest to 23:30 albo 00:30 UTC),
#   GoldAdvisorTrain  - ponowna walidacja i uczenie modelu (main.py train) w sobotę o 08:00.
# Uruchom RĘCZNIE: powershell -ExecutionPolicy Bypass -File install_daily_task.ps1
# Źródło danych wybiera się samo: OANDA, gdy ustawiona jest zmienna użytkownika OANDA_TOKEN, inaczej Yahoo+FRED.
param(
    [string]$Python = "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
    [string]$DailyAt = "01:30",
    [string]$TrainAt = "08:00"
)

$dir = $PSScriptRoot
if (-not (Test-Path $Python)) { throw "Nie znaleziono Pythona: $Python" }
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 30)

$daily = New-ScheduledTaskAction -Execute $Python -Argument "main.py daily" -WorkingDirectory $dir
$dailyTrigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Tuesday, Wednesday, Thursday, Friday, Saturday -At $DailyAt
Register-ScheduledTask -TaskName "GoldAdvisorDaily" -Action $daily -Trigger $dailyTrigger -Settings $settings `
    -Description "Doradca XAU/USD: werdykt dzienny" -Force | Out-Null

$train = New-ScheduledTaskAction -Execute $Python -Argument "main.py train" -WorkingDirectory $dir
$trainTrigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Saturday -At $TrainAt
Register-ScheduledTask -TaskName "GoldAdvisorTrain" -Action $train -Trigger $trainTrigger -Settings $settings `
    -Description "Doradca XAU/USD: walidacja i uczenie modelu" -Force | Out-Null

Write-Host "Zarejestrowano GoldAdvisorDaily (wt-sob $DailyAt, czyli po sesjach pon-pt) i GoldAdvisorTrain (sob $TrainAt)."
Write-Host "Usunięcie: Unregister-ScheduledTask -TaskName GoldAdvisorDaily,GoldAdvisorTrain -Confirm:`$false"
