@echo off
chcp 65001 >nul
title Story Studio 一键安装
powershell -ExecutionPolicy Bypass -File "%~dp0install.ps1"
pause
