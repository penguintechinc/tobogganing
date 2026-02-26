//go:build !xdp

package xdp

import "sync"

// NUMAPool is a non-NUMA-aware pool stub when built without the xdp tag.
// Uses standard sync.Pool without NUMA affinity.
type NUMAPool struct {
	bufSize int
	pool    sync.Pool
}

// NewNUMAPool creates a standard buffer pool (no NUMA affinity).
func NewNUMAPool(_, bufSize int) *NUMAPool {
	p := &NUMAPool{bufSize: bufSize}
	p.pool = sync.Pool{
		New: func() interface{} {
			return make([]byte, p.bufSize)
		},
	}
	return p
}

// Get returns a buffer from the pool.
func (p *NUMAPool) Get() []byte {
	return p.pool.Get().([]byte)
}

// Put returns a buffer to the pool.
func (p *NUMAPool) Put(buf []byte) {
	p.pool.Put(buf)
}

// DetectNUMANode returns 0 without XDP build tag.
func DetectNUMANode(_ string) (int, error) {
	return 0, nil
}
