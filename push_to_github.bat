@echo off
title Push Restock Smarter to GitHub
cd /d "%~dp0"
echo ========================================================
echo Push Restock Smarter to GitHub
echo ========================================================
echo.
set /p REPO_URL="Paste your GitHub Repository URL (e.g. https://github.com/GhibliFan99/restock-smarter.git): "
if "%REPO_URL%"=="" (
    echo No URL entered. Exiting.
    pause
    exit /b
)

git remote remove origin 2>nul
git remote add origin %REPO_URL%
git branch -M main
git push -u origin main

echo.
echo ========================================================
echo Done! Now connect your repository on dashboard.render.com
echo ========================================================
pause
