import axios from 'axios';

/**
 * ADAPTER NOTE (assumed contract): the Go test engine
 * (`engines/testserver/internal/handlers/speedtest_handlers.go`) mounts
 * `/speedtest/{download,upload,ping,info,result}` outside the authenticated
 * `/api/v1` router group and explicitly serves them without auth ("no auth
 * required for public speedtest functionality" per `cmd/testserver/main.go`).
 * There is no hub-api proxy for these routes today (verified: no
 * `speedtest` references in `hub_api/`). Self-service browser testing must
 * therefore hit the engine's own origin directly, similar to how
 * `LiveTestPage` lets an operator type a free-text `target` host. We reuse
 * that pattern: the caller supplies `serverUrl` (engine origin, e.g.
 * `https://waddleperf.example.com` or `''` for same-origin), and this
 * module talks to `${serverUrl}/speedtest/*` with a dedicated,
 * unauthenticated axios instance rather than the shared `apiClient` --
 * sending the portal's bearer token to an arbitrary/external engine origin
 * would leak it. If/when a hub-api proxy for these routes is added, swap
 * this instance for `apiClient` and prefix paths with `/perftest_cluster`.
 */
const speedtestClient = axios.create({ timeout: 30000 });

// The Web Crypto API caps a single getRandomValues() call at 65536 bytes
// (QuotaExceededError beyond that) -- fill larger upload payloads in chunks.
const MAX_RANDOM_CHUNK_BYTES = 65536;

function fillRandom(bytes: Uint8Array): void {
  for (let offset = 0; offset < bytes.length; offset += MAX_RANDOM_CHUNK_BYTES) {
    crypto.getRandomValues(bytes.subarray(offset, offset + MAX_RANDOM_CHUNK_BYTES));
  }
}

export interface SpeedTestInfo {
  name: string;
  version: string;
  max_chunk_size_mb: number;
  default_chunk_size_mb: number;
  recommended_streams: number;
  max_streams: number;
}

export interface UploadApiResponse {
  success: boolean;
  bytes_received: number;
  duration_ms: number;
  throughput_mbps: number;
}

export interface PingResult {
  latencyMs: number;
  jitterMs: number;
  samples: number[];
}

export interface DownloadResult {
  mbps: number;
  bytes: number;
  durationMs: number;
}

export interface UploadResult {
  mbps: number;
  bytes: number;
  durationMs: number;
}

export interface SpeedTestResultPayload {
  download_mbps: number;
  upload_mbps: number;
  latency_ms: number;
  jitter_ms: number;
  server_url: string;
}

/** One instantaneous throughput reading, derived from axios progress ticks mid-transfer. */
export interface ProgressSample {
  timestamp: number;
  mbps: number;
}

type SampleCallback = (sample: ProgressSample) => void;

/** Fetches engine capabilities (max chunk size, recommended stream count). */
export async function getSpeedTestInfo(serverUrl: string): Promise<SpeedTestInfo> {
  console.log('[speedtest] getSpeedTestInfo');
  const response = await speedtestClient.get<SpeedTestInfo>(`${serverUrl}/speedtest/info`);
  return response.data;
}

/**
 * Runs `samples` round trips against `/speedtest/ping` and derives average
 * latency plus jitter (max-min spread) client-side, since the engine's pong
 * response only echoes a server timestamp.
 */
export async function runPingTest(serverUrl: string, samples = 5): Promise<PingResult> {
  console.log('[speedtest] runPingTest', { samples });
  const rtts: number[] = [];

  for (let i = 0; i < samples; i += 1) {
    const start = performance.now();
    // eslint-disable-next-line no-await-in-loop -- ping RTT must be sequential
    await speedtestClient.get(`${serverUrl}/speedtest/ping`);
    rtts.push(performance.now() - start);
  }

  const latencyMs = rtts.reduce((sum, v) => sum + v, 0) / rtts.length;
  const jitterMs = Math.max(...rtts) - Math.min(...rtts);

  return { latencyMs, jitterMs, samples: rtts };
}

/**
 * Downloads a `sizeMB` chunk and computes throughput client-side from wall
 * time. When `onSample` is given, emits an instantaneous Mbps reading on
 * every axios download-progress tick so callers can drive a realtime chart.
 */
export async function runDownloadTest(
  serverUrl: string,
  sizeMB = 10,
  onSample?: SampleCallback
): Promise<DownloadResult> {
  console.log('[speedtest] runDownloadTest', { sizeMB });
  const start = performance.now();
  let lastLoaded = 0;
  let lastTick = start;

  const response = await speedtestClient.get<ArrayBuffer>(
    `${serverUrl}/speedtest/download?size=${sizeMB}`,
    {
      responseType: 'arraybuffer',
      onDownloadProgress: (event) => {
        const now = performance.now();
        const deltaBytes = event.loaded - lastLoaded;
        const deltaMs = now - lastTick;
        if (onSample && deltaMs > 0) {
          onSample({ timestamp: now, mbps: (deltaBytes * 8) / (deltaMs / 1000) / 1_000_000 });
        }
        lastLoaded = event.loaded;
        lastTick = now;
      },
    }
  );
  const durationMs = performance.now() - start;
  const bytes = response.data.byteLength;
  const mbps = durationMs > 0 ? (bytes * 8) / (durationMs / 1000) / 1_000_000 : 0;

  return { mbps, bytes, durationMs };
}

/**
 * Uploads a `sizeMB` random payload; trusts the engine's server-computed
 * throughput for the final result but also emits per-tick samples (via
 * `onSample`) from axios upload-progress events for the realtime chart.
 */
export async function runUploadTest(
  serverUrl: string,
  sizeMB = 10,
  onSample?: SampleCallback
): Promise<UploadResult> {
  console.log('[speedtest] runUploadTest', { sizeMB });
  const bytes = new Uint8Array(sizeMB * 1024 * 1024);
  fillRandom(bytes);
  let lastLoaded = 0;
  let lastTick = performance.now();

  const response = await speedtestClient.post<UploadApiResponse>(
    `${serverUrl}/speedtest/upload`,
    bytes,
    {
      headers: { 'Content-Type': 'application/octet-stream' },
      onUploadProgress: (event) => {
        const now = performance.now();
        const deltaBytes = event.loaded - lastLoaded;
        const deltaMs = now - lastTick;
        if (onSample && deltaMs > 0) {
          onSample({ timestamp: now, mbps: (deltaBytes * 8) / (deltaMs / 1000) / 1_000_000 });
        }
        lastLoaded = event.loaded;
        lastTick = now;
      },
    }
  );

  return {
    mbps: response.data.throughput_mbps,
    bytes: response.data.bytes_received,
    durationMs: response.data.duration_ms,
  };
}

/** Persists a completed test summary to the engine's result store. */
export async function submitSpeedTestResult(
  serverUrl: string,
  payload: SpeedTestResultPayload
): Promise<void> {
  console.log('[speedtest] submitSpeedTestResult');
  await speedtestClient.post(`${serverUrl}/speedtest/result`, payload);
}
