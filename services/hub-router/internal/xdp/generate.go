//go:build ignore

package xdp

//go:generate go run github.com/cilium/ebpf/cmd/bpf2go -cc clang -type xdp_stats bpf ../../bpf/xdp_ratelimit.c
