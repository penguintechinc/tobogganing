//go:build xdp

package xdp

import (
	"fmt"
	"net"
	"unsafe"

	"golang.org/x/sys/unix"
	log "github.com/sirupsen/logrus"
)

// AF_XDP socket setsockopt option numbers (linux/if_xdp.h).
const (
	xdpRxRing             = 6  // XDP_RX_RING
	xdpTxRing             = 7  // XDP_TX_RING
	xdpUmemReg            = 8  // XDP_UMEM_REG
	xdpUmemFillRing       = 9  // XDP_UMEM_FILL_RING
	xdpUmemCompletionRing = 10 // XDP_UMEM_COMPLETION_RING

	afxdpUmemFrameSize  = 4096 // Default UMEM frame size in bytes.
	afxdpRingSize       = 2048 // Default ring descriptor count (must be power of 2).
	afxdpUmemFrameCount = 4096 // Default total UMEM frames.
)

// xdpUmemReg is the kernel struct for XDP_UMEM_REG setsockopt (linux/if_xdp.h).
type xdpUmemRegKernel struct {
	addr      uint64
	len       uint64
	chunkSize uint32
	headroom  uint32
	flags     uint32
	_         [4]byte // alignment padding
}

// xdpSockaddrXDP is the kernel sockaddr for AF_XDP bind (linux/if_xdp.h).
type xdpSockaddrXDP struct {
	family   uint16
	flags    uint16
	ifindex  uint32
	queueID  uint32
	sharedFD uint32
}

// AFXDPSocket provides zero-copy packet delivery from NIC to userspace,
// bypassing the kernel network stack for the WireGuard proxy fast path.
type AFXDPSocket struct {
	fd       int
	umem     []byte
	queueID  int
	iface    string
	numaNode int
}

// NewAFXDPSocket creates an AF_XDP socket bound to a specific NIC queue.
// UMEM is allocated on the specified NUMA node for optimal locality.
func NewAFXDPSocket(iface string, queueID, numaNode int) (*AFXDPSocket, error) {
	ifIndex, err := getIfaceIndex(iface)
	if err != nil {
		return nil, fmt.Errorf("afxdp: interface %s not found: %w", iface, err)
	}

	fd, err := unix.Socket(unix.AF_XDP, unix.SOCK_RAW, 0)
	if err != nil {
		return nil, fmt.Errorf("afxdp: failed to create socket on %s queue %d: %w", iface, queueID, err)
	}

	// Allocate UMEM via mmap.
	umemSize := afxdpUmemFrameCount * afxdpUmemFrameSize
	umem, err := unix.Mmap(-1, 0, umemSize, unix.PROT_READ|unix.PROT_WRITE,
		unix.MAP_PRIVATE|unix.MAP_ANONYMOUS)
	if err != nil {
		unix.Close(fd)
		return nil, fmt.Errorf("afxdp: failed to allocate UMEM: %w", err)
	}

	// Apply NUMA binding when a specific node is requested.
	// golang.org/x/sys does not export Mbind directly; call the syscall manually.
	if numaNode >= 0 {
		nodemask := uint64(1) << uint(numaNode)
		maxnode := uint64(numaNode + 2)
		_, _, mbErrno := unix.Syscall6(unix.SYS_MBIND,
			uintptr(unsafe.Pointer(&umem[0])),
			uintptr(umemSize),
			2, // MPOL_BIND
			uintptr(unsafe.Pointer(&nodemask)),
			uintptr(maxnode),
			0)
		if mbErrno != 0 {
			log.WithError(mbErrno).WithField("node", numaNode).
				Debug("NUMA mbind failed (continuing with default placement)")
		}
	}

	// Register UMEM with the kernel via XDP_UMEM_REG setsockopt.
	reg := xdpUmemRegKernel{
		addr:      uint64(uintptr(unsafe.Pointer(&umem[0]))),
		len:       uint64(umemSize),
		chunkSize: afxdpUmemFrameSize,
	}
	if err := setsockoptRaw(fd, unix.SOL_XDP, xdpUmemReg,
		unsafe.Pointer(&reg), unsafe.Sizeof(reg)); err != nil {
		unix.Munmap(umem)
		unix.Close(fd)
		return nil, fmt.Errorf("afxdp: XDP_UMEM_REG failed: %w", err)
	}

	// Configure ring sizes for fill, completion, RX, and TX rings.
	ringN := uint32(afxdpRingSize)
	for _, opt := range []int{xdpUmemFillRing, xdpUmemCompletionRing, xdpRxRing, xdpTxRing} {
		if err := unix.SetsockoptInt(fd, unix.SOL_XDP, opt, int(ringN)); err != nil {
			unix.Munmap(umem)
			unix.Close(fd)
			return nil, fmt.Errorf("afxdp: ring option %d failed: %w", opt, err)
		}
	}

	// Bind the socket to the specified interface queue.
	sa := xdpSockaddrXDP{
		family:  unix.AF_XDP,
		ifindex: uint32(ifIndex),
		queueID: uint32(queueID),
	}
	_, _, bindErrno := unix.Syscall(unix.SYS_BIND, uintptr(fd),
		uintptr(unsafe.Pointer(&sa)), unsafe.Sizeof(sa))
	if bindErrno != 0 {
		unix.Munmap(umem)
		unix.Close(fd)
		return nil, fmt.Errorf("afxdp: bind to %s queue %d failed: %w", iface, queueID, bindErrno)
	}

	s := &AFXDPSocket{
		fd:       fd,
		umem:     umem,
		queueID:  queueID,
		iface:    iface,
		numaNode: numaNode,
	}

	log.WithFields(log.Fields{
		"interface": iface,
		"queue":     queueID,
		"numa_node": numaNode,
	}).Info("AF_XDP socket created")

	return s, nil
}

// Receive returns a batch of received packets from the RX ring.
// Blocks via poll(2) until at least one packet is available.
func (s *AFXDPSocket) Receive() ([][]byte, error) {
	if s.fd < 0 {
		return nil, fmt.Errorf("afxdp: socket not initialized")
	}

	fds := []unix.PollFd{{Fd: int32(s.fd), Events: unix.POLLIN}}
	n, err := unix.Poll(fds, -1)
	if err != nil {
		return nil, fmt.Errorf("afxdp: poll error: %w", err)
	}
	if n == 0 || fds[0].Revents&unix.POLLIN == 0 {
		return nil, nil
	}

	buf := make([]byte, afxdpUmemFrameSize)
	nread, err := unix.Read(s.fd, buf)
	if err != nil {
		return nil, fmt.Errorf("afxdp: read error: %w", err)
	}
	if nread <= 0 {
		return nil, nil
	}

	pkt := make([]byte, nread)
	copy(pkt, buf[:nread])
	return [][]byte{pkt}, nil
}

// Transmit sends a batch of packets via the TX ring.
func (s *AFXDPSocket) Transmit(pkts [][]byte) error {
	if s.fd < 0 {
		return fmt.Errorf("afxdp: socket not initialized")
	}

	for _, pkt := range pkts {
		if _, err := unix.Write(s.fd, pkt); err != nil {
			return fmt.Errorf("afxdp: transmit error: %w", err)
		}
	}
	return nil
}

// Close detaches the AF_XDP socket and frees UMEM.
func (s *AFXDPSocket) Close() {
	if s.fd >= 0 {
		if err := unix.Close(s.fd); err != nil {
			log.WithError(err).Warn("Error closing AF_XDP socket fd")
		}
		s.fd = -1
	}
	if s.umem != nil {
		if err := unix.Munmap(s.umem); err != nil {
			log.WithError(err).Warn("Error freeing AF_XDP UMEM")
		}
		s.umem = nil
	}
	log.WithFields(log.Fields{
		"interface": s.iface,
		"queue":     s.queueID,
	}).Info("AF_XDP socket closed")
}

// getIfaceIndex returns the OS interface index for the named interface.
func getIfaceIndex(name string) (int, error) {
	iface, err := net.InterfaceByName(name)
	if err != nil {
		return 0, err
	}
	return iface.Index, nil
}

// setsockoptRaw calls setsockopt(2) with an arbitrary struct pointer.
func setsockoptRaw(fd, level, opt int, p unsafe.Pointer, size uintptr) error {
	_, _, errno := unix.Syscall6(unix.SYS_SETSOCKOPT,
		uintptr(fd), uintptr(level), uintptr(opt), uintptr(p), size, 0)
	if errno != 0 {
		return errno
	}
	return nil
}
