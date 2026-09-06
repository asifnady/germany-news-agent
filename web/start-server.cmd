@echo off
rem Germany News web server launcher (hidden VBS in Startup folder runs this)
"C:\Program Files\nodejs\node.exe" "C:\Users\anade\projects\germany-news-agent\web\server.js" >> "C:\Users\anade\projects\germany-news-agent\web\server.log" 2>&1
