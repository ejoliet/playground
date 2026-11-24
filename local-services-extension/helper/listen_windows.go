package main

import (
	"context"
	"encoding/csv"
	"os/exec"
	"strings"
	"syscall"
)

func systemCommand(ctx context.Context, command string, args ...string) ([]byte, error) {
	cmd := exec.CommandContext(ctx, command, args...)
	cmd.SysProcAttr = &syscall.SysProcAttr{HideWindow: true}
	return cmd.Output()
}

func enumerate(ctx context.Context) ([]listener, error) {
	data, err := systemCommand(ctx, "netstat.exe", "-ano")
	if err != nil {
		return nil, err
	}
	processes := map[string]string{}
	if tasks, err := systemCommand(ctx, "tasklist.exe", "/FO", "CSV", "/NH"); err == nil {
		reader := csv.NewReader(strings.NewReader(string(tasks)))
		reader.FieldsPerRecord = -1
		if rows, err := reader.ReadAll(); err == nil {
			for _, row := range rows {
				if len(row) >= 2 {
					processes[row[1]] = row[0]
				}
			}
		}
	}
	var found []listener
	for _, line := range strings.Split(string(data), "\n") {
		fields := strings.Fields(line)
		if len(fields) != 5 || fields[0] != "TCP" || (fields[2] != "0.0.0.0:0" && fields[2] != "[::]:0") {
			continue
		}
		if item, ok := splitEndpoint(fields[1], false, processes[fields[4]]); ok {
			found = append(found, item)
		}
	}
	return found, nil
}
