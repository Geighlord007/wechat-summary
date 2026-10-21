@echo off
rem Register the daily WeChat group summary task (interactive logon only, no console window).
rem NOTE: keep this file ASCII-only; cmd.exe parses .bat as GBK and chokes on UTF-8 comments.
set PYTHONW=%~dp0.venv\Scripts\pythonw.exe
set SCRIPT=%~dp0run_daily.py

schtasks /delete /tn "WechatGroupDailySummary" /f >nul 2>&1
schtasks /create /tn "WechatGroupDailySummary" /tr "\"%PYTHONW%\" \"%SCRIPT%\"" /sc daily /st 09:07 /f
if %errorlevel% equ 0 (
    echo OK: task registered, runs daily at 09:07
    schtasks /query /tn "WechatGroupDailySummary" /fo list
) else (
    echo FAIL: schtasks returned %errorlevel%
    exit /b 1
)
