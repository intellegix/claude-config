@echo off
title Claude Browser Bridge MCP
echo Starting Claude Browser Bridge...
node "%~dp0server.js" --standalone
pause
