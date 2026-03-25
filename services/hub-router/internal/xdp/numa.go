//go:build xdp

package xdp

import (
	"fmt"
	"os"
	"strconv"
	"strings"
	"sync"
	"unsafe"

	"golang.org/x/sys/unix"
	log "github.com/sirupsen/logrus"
)

// NUMAPool provides NUMA-aware buffer pools for zero-copy packet processing.
// Buffers are allocated on the target NUMA node via mmap with MPOL_BIND,
// ensuring NIC → CPU → memory all on the same NUMA node.
type NUMAPool struct {
	node    int
	bufSize int
	pool    sync.Pool
}

// NewNUMAPool creates a buffer pool pinned to the specified NUMA node.
func NewNUMAPool(node, bufSize int) *NUMAPool {
	p := &NUMAPool{
		node:    node,
		bufSize: bufSize,
	}

	p.pool = sync.Pool{
		New: func() interface{} {
			return p.allocNUMA()
		},
	}

	log.WithFields(log.Fields{
		"numa_node": node,
		"buf_size":  bufSize,
	}).Debug("NUMA pool created")

	return p
}

// Get returns a buffer from the NUMA-local pool.
func (p *NUMAPool) Get() []byte {
	return p.pool.Get().([]byte)
}

// Put returns a buffer to the pool.
func (p *NUMAPool) Put(buf []byte) {
	p.pool.Put(buf)
}

// allocNUMA allocates a buffer on the target NUMA node using mmap + mbind.
func (p *NUMAPool) allocNUMA() []byte {
	// Allocate via mmap
	buf, err := unix.Mmap(-1, 0, p.bufSize, unix.PROT_READ|unix.PROT_WRITE,
		unix.MAP_PRIVATE|unix.MAP_ANONYMOUS)
	if err != nil {
		// Fallback to regular allocation
		log.WithError(err).Debug("NUMA mmap failed, falling back to regular allocation")
		return make([]byte, p.bufSize)
	}

	// Bind to NUMA node via mbind syscall (MPOL_BIND = 2, SYS_MBIND = 237).
	// golang.org/x/sys does not export Mbind directly; call the syscall manually.
	nodemask := uint64(1) << uint(p.node)
	maxnode := uint64(p.node + 2)
	_, _, errno := unix.Syscall6(unix.SYS_MBIND,
		uintptr(unsafe.Pointer(&buf[0])),
		uintptr(p.bufSize),
		2, // MPOL_BIND
		uintptr(unsafe.Pointer(&nodemask)),
		uintptr(maxnode),
		0)
	if errno != 0 {
		log.WithError(errno).WithField("node", p.node).Debug("NUMA mbind failed (continuing with default placement)")
	}

	return buf
}

// DetectNUMANode reads the NUMA node for a network interface from sysfs.
func DetectNUMANode(iface string) (int, error) {
	path := fmt.Sprintf("/sys/class/net/%s/device/numa_node", iface)
	data, err := os.ReadFile(path)
	if err != nil {
		return 0, fmt.Errorf("numa: failed to read %s: %w", path, err)
	}

	node, err := strconv.Atoi(strings.TrimSpace(string(data)))
	if err != nil {
		return 0, fmt.Errorf("numa: invalid node value in %s: %w", path, err)
	}

	// -1 means no NUMA affinity (virtual device), treat as node 0
	if node < 0 {
		node = 0
	}

	return node, nil
}
