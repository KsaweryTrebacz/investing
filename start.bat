@echo off
setlocal enabledelayedexpansion
title Aurum Invest - Platforma Inwestycyjna w Zloto

set "INDEX_FILE=%~dp0index.html"
set "BROWSER_EXE="

:: 1. Szukaj Edge w typowych lokalizacjach
if exist "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" set "BROWSER_EXE=C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
if not defined BROWSER_EXE if exist "C:\Program Files\Microsoft\Edge\Application\msedge.exe" set "BROWSER_EXE=C:\Program Files\Microsoft\Edge\Application\msedge.exe"
if not defined BROWSER_EXE if exist "C:\Program Files\Google\Chrome\Application\chrome.exe" set "BROWSER_EXE=C:\Program Files\Google\Chrome\Application\chrome.exe"
if not defined BROWSER_EXE if exist "C:\Program Files (x86)\Google\Chrome\Application\chrome.exe" set "BROWSER_EXE=C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"

:: 2. Szukaj EdgeCore jesli standardowa sciezka jest inna
if not defined BROWSER_EXE (
  for /r "C:\Program Files (x86)\Microsoft\EdgeCore" %%f in (msedge.exe) do (
    if exist "%%f" (
      set "BROWSER_EXE=%%f"
      goto foundBrowser
    )
  )
)

:foundBrowser
if defined BROWSER_EXE (
  echo Uruchamianie w nowoczesnej przegladarce: %BROWSER_EXE%
  start "" "%BROWSER_EXE%" "%INDEX_FILE%"
) else (
  echo Uruchamianie w domyslnej przegladarce systemowej...
  start "" "%INDEX_FILE%"
)

exit
