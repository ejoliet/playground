package main

import (
	"context"
	"crypto/tls"
	"encoding/binary"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net"
	"net/http"
	"net/netip"
	"net/url"
	"os"
	"sort"
	"strconv"
	"strings"
	"sync"
	"time"
)

var extensionOrigin string
var version = "dev"

const protocolVersion = 1
const maxMessage = 1 << 20

type request struct {
	Command string `json:"command"`
	Version int    `json:"version"`
}

type response struct {
	Version       int       `json:"version"`
	HelperVersion string    `json:"helperVersion"`
	Error         string    `json:"error,omitempty"`
	Checked       int       `json:"checked"`
	Services      []service `json:"services"`
}

type listener struct {
	address string
	port    uint16
	process string
}

type service struct {
	URL      string `json:"url"`
	Address  string `json:"address"`
	Port     uint16 `json:"port"`
	Protocol string `json:"protocol"`
	Process  string `json:"process"`
	Status   int    `json:"status"`
}

func main() {
	if handled, err := runSetup(os.Args[1:]); handled {
		if err != nil {
			fmt.Fprintln(os.Stderr, err)
			os.Exit(1)
		}
		return
	}
	// Chrome supplies the caller's origin as the first argument, followed by
	// additional platform-specific arguments.
	if extensionOrigin == "" || len(os.Args) < 2 ||
		strings.TrimSuffix(os.Args[1], "/") != strings.TrimSuffix(extensionOrigin, "/") {
		fmt.Fprintln(os.Stderr, "Local Services Helper is launched by its Chrome extension.")
		os.Exit(1)
	}
	command, err := readRequest(os.Stdin)
	result := response{Version: protocolVersion, HelperVersion: version, Services: []service{}}
	switch {
	case err != nil:
		result.Error = "Invalid discovery request."
	case command.Version != protocolVersion:
		result.Error = "The extension and helper use different versions. Reinstall the helper from Setup."
	case command.Command == "ping":
		// Check registration without reading the listener table.
	case command.Command == "discover":
		ctx, cancel := context.WithTimeout(context.Background(), 25*time.Second)
		defer cancel()
		go func() {
			// A disconnected Chrome port closes stdin. Stop pending probes.
			_, _ = io.Copy(io.Discard, os.Stdin)
			cancel()
		}()
		result.Services, result.Checked, err = discover(ctx)
		if err != nil {
			result.Error = err.Error()
		}
	default:
		result.Error = "Unknown discovery command."
	}
	if err := writeResponse(os.Stdout, result); err != nil {
		fmt.Fprintln(os.Stderr, "Could not send the discovery result:", err)
		os.Exit(1)
	}
}

func readRequest(in io.Reader) (request, error) {
	var size uint32
	var value request
	if err := binary.Read(in, binary.NativeEndian, &size); err != nil {
		return value, err
	}
	if size == 0 || size > 4096 {
		return value, errors.New("invalid request length")
	}
	data := make([]byte, size)
	if _, err := io.ReadFull(in, data); err != nil {
		return value, err
	}
	return value, json.Unmarshal(data, &value)
}

func writeResponse(out io.Writer, response response) error {
	data, err := json.Marshal(response)
	if err != nil {
		return err
	}
	if len(data) > maxMessage {
		response.Services = nil
		response.Error = "The discovery result is larger than Chrome can receive."
		return writeResponse(out, response)
	}
	if err := binary.Write(out, binary.NativeEndian, uint32(len(data))); err != nil {
		return err
	}
	_, err = out.Write(data)
	return err
}

func splitEndpoint(endpoint string, ipv6 bool, process string) (listener, bool) {
	address, portText, ok := strings.Cut(strings.TrimSpace(endpoint), "]:")
	if ok {
		address = strings.TrimPrefix(address, "[")
	} else {
		lastColon := strings.LastIndexByte(endpoint, ':')
		if lastColon < 1 {
			return listener{}, false
		}
		address, portText = endpoint[:lastColon], endpoint[lastColon+1:]
	}
	port, err := strconv.ParseUint(portText, 10, 16)
	if err != nil || port == 0 {
		return listener{}, false
	}
	if address == "*" {
		address = "0.0.0.0"
		if ipv6 {
			address = "::"
		}
	}
	ip, err := netip.ParseAddr(address)
	if err != nil {
		return listener{}, false
	}
	ip = ip.Unmap()
	if ip.IsUnspecified() {
		if ip.Is6() {
			ip = netip.IPv6Loopback()
		} else {
			ip = netip.MustParseAddr("127.0.0.1")
		}
	}
	return listener{address: ip.String(), port: uint16(port), process: process}, true
}

func discover(ctx context.Context) ([]service, int, error) {
	found, err := enumerate(ctx)
	if err != nil {
		return nil, 0, fmt.Errorf("Could not read the local listener list: %w", err)
	}
	targets := make(map[string]listener)
	for _, item := range found {
		key := net.JoinHostPort(item.address, strconv.Itoa(int(item.port)))
		if existing, ok := targets[key]; !ok || existing.process == "" {
			targets[key] = item
		}
	}

	// No proxy, cookies, redirects, or response bodies. Certificate verification
	// is skipped for protocol identification only. Chrome verifies opened URLs.
	transport := &http.Transport{
		DisableKeepAlives:      true,
		DialContext:            (&net.Dialer{Timeout: 700 * time.Millisecond}).DialContext,
		TLSHandshakeTimeout:    700 * time.Millisecond,
		ResponseHeaderTimeout:  700 * time.Millisecond,
		MaxResponseHeaderBytes: 32 << 10,
		TLSClientConfig:        &tls.Config{InsecureSkipVerify: true, MinVersion: tls.VersionTLS12},
		ForceAttemptHTTP2:      true,
	}
	client := &http.Client{
		Transport: transport,
		Timeout:   time.Second,
		CheckRedirect: func(_ *http.Request, _ []*http.Request) error {
			return http.ErrUseLastResponse
		},
	}
	defer transport.CloseIdleConnections()

	jobs := make(chan listener)
	hits := make(chan service, len(targets))
	var workers sync.WaitGroup
	for range min(24, len(targets)) {
		workers.Add(1)
		go func() {
			defer workers.Done()
			for item := range jobs {
				if value, ok := identify(ctx, client, item); ok {
					hits <- value
				}
			}
		}()
	}
	go func() {
		defer close(jobs)
		for _, item := range targets {
			select {
			case jobs <- item:
			case <-ctx.Done():
				return
			}
		}
	}()
	workers.Wait()
	close(hits)

	services := make([]service, 0, len(hits))
	for value := range hits {
		services = append(services, value)
	}
	sort.Slice(services, func(i, j int) bool {
		if services[i].Port != services[j].Port {
			return services[i].Port < services[j].Port
		}
		return services[i].URL < services[j].URL
	})
	if ctx.Err() != nil {
		return services, len(targets), errors.New("Discovery stopped before all listeners could be checked.")
	}
	return services, len(targets), nil
}

func identify(ctx context.Context, client *http.Client, item listener) (service, bool) {
	for _, protocol := range []string{"https", "http"} {
		address := net.JoinHostPort(item.address, strconv.Itoa(int(item.port)))
		target := (&url.URL{Scheme: protocol, Host: address, Path: "/"}).String()
		req, err := http.NewRequestWithContext(ctx, http.MethodHead, target, nil)
		if err != nil {
			continue
		}
		req.Header.Set("User-Agent", "Local Services Helper")
		result, err := client.Do(req)
		if err != nil {
			continue
		}
		_ = result.Body.Close()
		return service{
			URL: target, Address: item.address, Port: item.port, Protocol: protocol,
			Process: item.process, Status: result.StatusCode,
		}, true
	}
	return service{}, false
}
