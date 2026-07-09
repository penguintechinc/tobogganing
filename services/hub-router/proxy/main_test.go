// Package main implements the SASEWaddle headend proxy server.
package main

import "testing"

func TestTokenMatchConstantTime(t *testing.T) {
	if !tokensEqual("abc", "abc") {
		t.Fatal("equal tokens should match")
	}
	if tokensEqual("abc", "abd") {
		t.Fatal("different tokens must not match")
	}
	if tokensEqual("", "") {
		t.Fatal("empty expected token must never match")
	}
}
