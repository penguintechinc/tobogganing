module github.com/tobogganing/k8s-cni

go 1.23.1

require (
	github.com/containernetworking/cni v1.2.3
	github.com/containernetworking/plugins v1.5.1
	github.com/golang-jwt/jwt/v5 v5.2.0
	github.com/sirupsen/logrus v1.9.3
	github.com/vishvananda/netlink v1.1.0
	github.com/vishvananda/netns v0.0.4
	golang.zx2c4.com/wireguard/wgctrl v0.0.0-20230429144221-925a1e7659e6
	k8s.io/apimachinery v0.30.3
	k8s.io/client-go v0.30.3
)

require (
	github.com/containernetworking/cnitool v1.0.0
	github.com/onsi/ginkgo/v2 v2.19.0
	github.com/onsi/gomega v1.33.1
	github.com/stretchr/testify v1.9.0
)