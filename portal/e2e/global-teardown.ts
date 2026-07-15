async function globalTeardown() {
  console.log('[Teardown] Stopping mock API server...');
  const mockApiProcess = (global as any).__mockApiProcess;
  if (mockApiProcess) {
    mockApiProcess.kill();
  }
}

export default globalTeardown;
