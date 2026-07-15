import { spawn } from 'child_process';
import { fileURLToPath } from 'url';
import { dirname, join } from 'path';

const __dirname = dirname(fileURLToPath(import.meta.url));

let mockApiProcess: ReturnType<typeof spawn>;

async function globalSetup() {
  console.log('[Setup] Starting mock API server on port 3001...');
  mockApiProcess = spawn('node', [join(__dirname, 'mock-api-runner.mjs')], {
    stdio: 'inherit',
  });

  // Wait a bit for the server to start
  await new Promise((resolve) => setTimeout(resolve, 1000));

  // Store the process in global state for cleanup in teardown
  (global as any).__mockApiProcess = mockApiProcess;
}

export default globalSetup;
