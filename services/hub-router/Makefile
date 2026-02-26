BPF_CLANG ?= clang
BPF_CFLAGS := -O2 -g -target bpf -D__TARGET_ARCH_x86

.PHONY: bpf-generate
bpf-generate: bpf/xdp_ratelimit.c
	$(BPF_CLANG) $(BPF_CFLAGS) -c bpf/xdp_ratelimit.c -o bpf/xdp_ratelimit.o
	cd internal/xdp && go generate ./...

.PHONY: build-xdp
build-xdp: bpf-generate
	go build -tags xdp -o bin/hub-router ./proxy/

.PHONY: build
build:
	go build -o bin/hub-router ./proxy/
