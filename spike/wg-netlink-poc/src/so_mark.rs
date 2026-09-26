//! Goal 2: SO_MARK connection marking, replacing the Go anti-pattern in
//! `proxy/wireguard_router.go::markTrafficAuthenticated`, which shells
//! `iptables -t mangle -A OUTPUT -s <addr> -j MARK --set-mark 100` **once
//! per connection** and never cleans the rule up (a permanent mangle-table
//! leak under sustained connection churn).
//!
//! Replacement: `setsockopt(fd, SOL_SOCKET, SO_MARK, mark)` on the proxied
//! socket itself (one syscall per connection, zero new firewall rules per
//! connection) + a single, static nftables rule applied once at startup
//! that matches on `meta mark` (see `nft_batch.rs`). The per-connection cost
//! drops from "shell out to `iptables`, parse text" to "one setsockopt call".

use std::io;
use std::os::unix::io::AsRawFd;

/// The fwmark value hub-router uses for traffic it has authenticated and
/// authorized to route (mirrors the Go code's `--set-mark 100`).
pub const AUTHENTICATED_MARK: u32 = 100;

/// Set `SO_MARK` on any socket-like type exposing a raw fd (works for
/// `TcpStream`, `tokio::net::TcpStream`, `UdpSocket`, etc. via `AsRawFd`).
///
/// NEEDS PRIVILEGED ENV: `SO_MARK` requires `CAP_NET_ADMIN` on the process
/// (per `man 7 socket`). In this sandbox this returns `EPERM` — the function
/// itself is fully implemented and the syscall shape is correct; only the
/// kernel's permission check can't be exercised here.
pub fn set_socket_mark<S: AsRawFd>(sock: &S, mark: u32) -> io::Result<()> {
    let fd = sock.as_raw_fd();
    let mark_c: libc::c_int = mark as libc::c_int;
    // Safety: fd is a valid, open socket fd for the lifetime of this call
    // (borrowed via &S), and we pass a correctly-sized c_int for SO_MARK's
    // expected option value per `man 7 socket`.
    let ret = unsafe {
        libc::setsockopt(
            fd,
            libc::SOL_SOCKET,
            libc::SO_MARK,
            &mark_c as *const _ as *const libc::c_void,
            std::mem::size_of::<libc::c_int>() as libc::socklen_t,
        )
    };
    if ret != 0 {
        return Err(io::Error::last_os_error());
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::net::TcpListener;

    /// VALIDATED (syscall shape): opens a real TCP socket and attempts to
    /// set SO_MARK. Without CAP_NET_ADMIN this fails with EPERM, which is
    /// the expected, non-panicking outcome we assert on — proving the
    /// setsockopt plumbing (fd, option level/name, buffer size) is correct
    /// up to the point the kernel's capability check rejects it.
    #[test]
    fn set_mark_fails_closed_without_net_admin() {
        let listener = TcpListener::bind("127.0.0.1:0").expect("bind loopback listener");
        match set_socket_mark(&listener, AUTHENTICATED_MARK) {
            Ok(()) => {
                // Running with CAP_NET_ADMIN elsewhere — also acceptable.
            }
            Err(e) => {
                assert_eq!(
                    e.raw_os_error(),
                    Some(libc::EPERM),
                    "expected EPERM without CAP_NET_ADMIN, got: {e:?}"
                );
            }
        }
    }
}
