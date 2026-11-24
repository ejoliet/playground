package main

import (
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"runtime"
	"strings"
)

const hostName = "io.github.ejoliet.local_services"
const helperName = "local-services-helper"

func runSetup(args []string) (bool, error) {
	if len(args) == 0 {
		return false, nil
	}
	switch args[0] {
	case "--install-macos", "--remove-macos":
		if runtime.GOOS != "darwin" {
			return true, errors.New("this installer is for macOS")
		}
		return true, setupMac(args[0] == "--install-macos")
	case "--write-windows-manifest":
		if runtime.GOOS != "windows" || len(args) != 2 || !filepath.IsAbs(args[1]) {
			return true, errors.New("expected the absolute Windows installation folder")
		}
		return true, writeManifest(filepath.Join(args[1], "host.json"), filepath.Join(args[1], helperName+".exe"))
	}
	return false, nil
}

func setupMac(install bool) error {
	home, err := os.UserHomeDir()
	if err != nil {
		return err
	}
	support := filepath.Join(home, "Library", "Application Support")
	binaryFolder := filepath.Join(support, "Local Services Helper")
	binary := filepath.Join(binaryFolder, helperName)
	manifest := filepath.Join(support, "Google", "Chrome", "NativeMessagingHosts", hostName+".json")
	if !install {
		for _, file := range []string{manifest, binary} {
			if err := os.Remove(file); err != nil && !errors.Is(err, os.ErrNotExist) {
				return err
			}
		}
		_ = os.Remove(binaryFolder)
		return nil
	}
	source, err := os.Executable()
	if err != nil {
		return err
	}
	data, err := os.ReadFile(source)
	if err != nil {
		return err
	}
	if err := writeFile(binary, data, 0755); err != nil {
		return err
	}
	return writeManifest(manifest, binary)
}

func writeManifest(destination, binary string) error {
	if extensionOrigin == "" {
		return errors.New("the helper is missing its Chrome extension ID")
	}
	manifest := struct {
		Name           string   `json:"name"`
		Description    string   `json:"description"`
		Path           string   `json:"path"`
		Type           string   `json:"type"`
		AllowedOrigins []string `json:"allowed_origins"`
	}{hostName, "Local Services Helper", binary, "stdio", []string{strings.TrimSuffix(extensionOrigin, "/") + "/"}}
	data, err := json.MarshalIndent(manifest, "", "  ")
	if err != nil {
		return err
	}
	return writeFile(destination, append(data, '\n'), 0600)
}

func writeFile(destination string, data []byte, mode os.FileMode) error {
	folder := filepath.Dir(destination)
	if err := os.MkdirAll(folder, 0700); err != nil {
		return err
	}
	file, err := os.CreateTemp(folder, ".local-services-*")
	if err != nil {
		return err
	}
	defer os.Remove(file.Name())
	if _, err := file.Write(data); err != nil {
		_ = file.Close()
		return err
	}
	if err := file.Close(); err != nil {
		return err
	}
	if err := os.Chmod(file.Name(), mode); err != nil {
		return err
	}
	if err := os.Rename(file.Name(), destination); err != nil {
		return fmt.Errorf("install %s: %w", filepath.Base(destination), err)
	}
	return nil
}
