package main

import (
	"bufio"
	"context"
	"encoding/binary"
	"encoding/hex"
	"errors"
	"fmt"
	"net"
	"os"
	"os/exec"
	"regexp"
	"strconv"
	"strings"
)

var ownerPattern = regexp.MustCompile(`\("([^"]+)",pid=`)

func enumerate(ctx context.Context) ([]listener, error) {
	var found []listener
	for _, version := range []string{"-4", "-6"} {
		data, err := exec.CommandContext(ctx, "ss", "-H", "-ltnp", version).Output()
		if err != nil {
			return procListeners()
		}
		for _, line := range strings.Split(string(data), "\n") {
			fields := strings.Fields(line)
			if len(fields) < 5 {
				continue
			}
			process := ""
			if match := ownerPattern.FindStringSubmatch(line); len(match) == 2 {
				process = match[1]
			}
			if item, ok := splitEndpoint(fields[3], version == "-6", process); ok {
				found = append(found, item)
			}
		}
	}
	return found, nil
}

func procListeners() ([]listener, error) {
	var found []listener
	for _, file := range []string{"/proc/net/tcp", "/proc/net/tcp6"} {
		items, err := readProc(file)
		if err != nil && !(file == "/proc/net/tcp6" && errors.Is(err, os.ErrNotExist)) {
			return nil, err
		}
		found = append(found, items...)
	}
	return found, nil
}

func readProc(path string) ([]listener, error) {
	file, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	defer file.Close()
	var found []listener
	scanner := bufio.NewScanner(file)
	for scanner.Scan() {
		fields := strings.Fields(scanner.Text())
		if len(fields) < 4 || fields[3] != "0A" {
			continue
		}
		address, port, ok := strings.Cut(fields[1], ":")
		if !ok {
			continue
		}
		raw, err := hex.DecodeString(address)
		number, portErr := strconv.ParseUint(port, 16, 16)
		if err != nil || portErr != nil || (len(raw) != 4 && len(raw) != 16) {
			continue
		}
		for i := 0; i < len(raw); i += 4 {
			chunk := raw[i : i+4]
			binary.BigEndian.PutUint32(chunk, binary.NativeEndian.Uint32(chunk))
		}
		endpoint := net.JoinHostPort(net.IP(raw).String(), fmt.Sprint(number))
		if item, ok := splitEndpoint(endpoint, len(raw) == 16, ""); ok {
			found = append(found, item)
		}
	}
	return found, scanner.Err()
}
