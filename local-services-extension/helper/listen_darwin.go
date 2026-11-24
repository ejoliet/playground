package main

import (
	"context"
	"os/exec"
	"strings"
)

func enumerate(ctx context.Context) ([]listener, error) {
	data, err := exec.CommandContext(ctx, "/usr/sbin/lsof", "-nP", "-iTCP", "-sTCP:LISTEN", "-Fctn").Output()
	if err != nil {
		exit, isExit := err.(*exec.ExitError)
		if !isExit || exit.ExitCode() != 1 || (len(data) == 0 && len(exit.Stderr) > 0) {
			return nil, err
		}
	}
	var found []listener
	var process string
	var ipv6 bool
	for _, line := range strings.Split(string(data), "\n") {
		if len(line) < 2 {
			continue
		}
		switch line[0] {
		case 'c':
			process = line[1:]
		case 't':
			ipv6 = line[1:] == "IPv6"
		case 'n':
			if item, ok := splitEndpoint(line[1:], ipv6, process); ok {
				found = append(found, item)
			}
		}
	}
	return found, nil
}
