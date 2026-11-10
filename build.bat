@echo off
echo Building TopoNet Prototype.pol Compiler (polc)...
gcc -O2 -std=c99 -Wall polc.c -o polc.exe -lm
if %ERRORLEVEL% EQU 0 (
    echo [SUCCESS] polc.exe built successfully!
    echo Run '.\polc.exe --help' to get started.
) else (
    echo [ERROR] Build failed with error code %ERRORLEVEL%.
)
