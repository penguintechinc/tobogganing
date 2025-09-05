module github.com/tobogganing/k8s-cni

go 1.23.1

require (
	github.com/containernetworking/cni v1.2.3
	github.com/sirupsen/logrus v1.9.3
	github.com/vishvananda/netlink v1.2.1-beta.2
	github.com/vishvananda/netns v0.0.4
	golang.zx2c4.com/wireguard/wgctrl v0.0.0-20230429144221-925a1e7659e6
	github.com/cilium/ebpf v0.15.0
	k8s.io/api v0.30.0
	k8s.io/apimachinery v0.30.0
	k8s.io/client-go v0.30.0
	github.com/gorilla/websocket v1.5.0
)

require github.com/stretchr/testify v1.9.0

require (
	github.com/davecgh/go-spew v1.1.1 // indirect
	github.com/google/go-cmp v0.6.0 // indirect
	github.com/josharian/native v1.1.0 // indirect
	github.com/mdlayher/genetlink v1.3.2 // indirect
	github.com/mdlayher/netlink v1.7.2 // indirect
	github.com/mdlayher/socket v0.4.1 // indirect
	github.com/pmezard/go-difflib v1.0.0 // indirect
	golang.org/x/crypto v0.23.0 // indirect
	golang.org/x/net v0.25.0 // indirect
	golang.org/x/sync v0.1.0 // indirect
	golang.org/x/sys v0.21.0 // indirect
	golang.zx2c4.com/wireguard v0.0.0-20230325221338-052af4a8072b // indirect
	gopkg.in/yaml.v3 v3.0.1 // indirect
)
