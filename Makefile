# TopoNet Prototype.pol Compiler (polc) Makefile
CC = gcc
CFLAGS = -O2 -Wall -std=c99
TARGET = polc.exe

all: $(TARGET)

$(TARGET): polc.c
	$(CC) $(CFLAGS) polc.c -o $(TARGET) -lm

clean:
	del /f $(TARGET) 2>nul || rm -f $(TARGET)

.PHONY: all clean
