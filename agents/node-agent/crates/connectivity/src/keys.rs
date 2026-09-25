//! WireGuard client keypair generation. Keys are x25519 (Curve25519 ECDH),
//! encoded as standard 44-character base64 strings on the wire — the same
//! format the `wg` CLI and every other WireGuard implementation use, and
//! what boringtun's own UAPI parser accepts directly.

use base64::{engine::general_purpose::STANDARD, Engine as _};
use boringtun::x25519::{PublicKey, StaticSecret};
use rand_core::OsRng;

/// A freshly generated WireGuard identity for this node: the private key
/// used to configure the local boringtun device, and the base64-encoded
/// public key advertised to the control plane in [`EnrollRequest::public_key`](node_agent_core::EnrollRequest::public_key).
pub struct WgKeypair {
    pub private_key: StaticSecret,
    pub public_key_b64: String,
}

/// Generates a new random x25519 keypair using the OS CSPRNG. Called once
/// per agent process lifetime at connectivity module startup — WireGuard
/// keys are not persisted across restarts in this design, matching the
/// Go reference client's re-registration-on-start behavior.
pub fn generate() -> WgKeypair {
    let private_key = StaticSecret::random_from_rng(OsRng);
    let public_key = PublicKey::from(&private_key);
    WgKeypair {
        private_key,
        public_key_b64: STANDARD.encode(public_key.as_bytes()),
    }
}

/// Base64-encodes a private key for the boringtun UAPI `private_key=`
/// field. Kept separate from [`generate`] so the control loop can re-encode
/// the same in-memory key on every config-apply without re-deriving it.
pub fn private_key_b64(secret: &StaticSecret) -> String {
    STANDARD.encode(secret.to_bytes())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn generate_produces_a_standard_44_char_base64_public_key() {
        let kp = generate();
        assert_eq!(kp.public_key_b64.len(), 44);
        assert!(STANDARD.decode(&kp.public_key_b64).is_ok());
    }

    #[test]
    fn generate_produces_distinct_keys_each_call() {
        let a = generate();
        let b = generate();
        assert_ne!(a.public_key_b64, b.public_key_b64);
    }

    #[test]
    fn private_key_b64_round_trips_through_base64() {
        let kp = generate();
        let encoded = private_key_b64(&kp.private_key);
        assert_eq!(encoded.len(), 44);
        let decoded = STANDARD.decode(&encoded).expect("valid base64");
        assert_eq!(decoded.len(), 32);
    }
}
