@echo off
title Restock Smarter - Live Server
cd /d "%~dp0"
echo ===================================================
echo Starting Restock Smarter with Shareable Public Link
echo ===================================================
python run_tunnel.py
pause

