package main

// Export package-private identifiers for testing.

var (
	// OS constants
	OSWindows = osWindows
	OSDarwin  = osDarwin
	OSLinux   = osLinux

	// CurrentGOOS allows tests to override platform dispatch.
	CurrentGOOS = &currentGOOS
)
