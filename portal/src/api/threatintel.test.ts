import apiClient from './client';
import {
  addBlocklistEntry,
  checkIoc,
  createFeed,
  deleteBlocklistEntry,
  deleteFeed,
  listBlocklist,
  listFeeds,
  refreshFeed,
} from './threatintel';

jest.mock('./client');
const mockApiClient = apiClient as jest.Mocked<typeof apiClient>;

const meta = { version: 1, timestamp: '2026-08-20T10:00:00Z' };

describe('threatintel API', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe('feeds', () => {
    it('lists feed sources', async () => {
      const sources = [
        {
          id: 'f1',
          name: 'my-misp',
          source_type: 'misp',
          url: 'https://misp.example.com/export.json',
          enabled: true,
          last_refresh_at: null,
          last_refresh_status: null,
          last_refresh_error: null,
          created_at: meta.timestamp,
        },
      ];
      mockApiClient.get.mockResolvedValue({ data: { sources, meta } });

      const result = await listFeeds();

      expect(mockApiClient.get).toHaveBeenCalledWith('/threatintel/feeds');
      expect(result).toEqual(sources);
    });

    it('creates a feed source', async () => {
      const source = {
        id: 'f1',
        name: 'my-misp',
        source_type: 'misp',
        url: 'https://misp.example.com/export.json',
        enabled: true,
        last_refresh_at: null,
        last_refresh_status: null,
        last_refresh_error: null,
        created_at: meta.timestamp,
      };
      mockApiClient.post.mockResolvedValue({ data: source });

      const result = await createFeed({
        name: 'my-misp',
        source_type: 'misp',
        url: 'https://misp.example.com/export.json',
      });

      expect(mockApiClient.post).toHaveBeenCalledWith('/threatintel/feeds', {
        name: 'my-misp',
        source_type: 'misp',
        url: 'https://misp.example.com/export.json',
      });
      expect(result).toEqual(source);
    });

    it('deletes a feed source', async () => {
      const message = { message: 'Feed source deleted successfully', meta };
      mockApiClient.delete.mockResolvedValue({ data: message });

      const result = await deleteFeed('f1');

      expect(mockApiClient.delete).toHaveBeenCalledWith('/threatintel/feeds/f1');
      expect(result).toEqual(message);
    });

    it('triggers a feed refresh', async () => {
      const refreshResult = {
        id: 'f1',
        status: 'completed',
        added: 10,
        updated: 2,
        errors: 0,
        meta,
      };
      mockApiClient.post.mockResolvedValue({ data: refreshResult });

      const result = await refreshFeed('f1');

      expect(mockApiClient.post).toHaveBeenCalledWith('/threatintel/feeds/f1/refresh');
      expect(result).toEqual(refreshResult);
    });
  });

  describe('blocklist', () => {
    it('lists blocklist entries with no filters', async () => {
      const entries = [
        {
          id: 'e1',
          indicator_type: 'domain',
          value: 'malicious.example.com',
          source: 'manual',
          confidence: 100,
          active: true,
          created_at: meta.timestamp,
          updated_at: meta.timestamp,
        },
      ];
      mockApiClient.get.mockResolvedValue({ data: { entries, meta } });

      const result = await listBlocklist();

      expect(mockApiClient.get).toHaveBeenCalledWith('/threatintel/blocklist', { params: {} });
      expect(result).toEqual(entries);
    });

    it('lists blocklist entries with filters', async () => {
      mockApiClient.get.mockResolvedValue({ data: { entries: [], meta } });

      await listBlocklist({ indicator_type: 'ip', source: 'misp' });

      expect(mockApiClient.get).toHaveBeenCalledWith('/threatintel/blocklist', {
        params: { indicator_type: 'ip', source: 'misp' },
      });
    });

    it('adds a blocklist entry', async () => {
      const entry = {
        id: 'e1',
        indicator_type: 'domain',
        value: 'malicious.example.com',
        source: 'manual',
        confidence: 100,
        active: true,
        created_at: meta.timestamp,
        updated_at: meta.timestamp,
      };
      mockApiClient.post.mockResolvedValue({ data: entry });

      const result = await addBlocklistEntry({
        indicator_type: 'domain',
        value: 'malicious.example.com',
      });

      expect(mockApiClient.post).toHaveBeenCalledWith('/threatintel/blocklist', {
        indicator_type: 'domain',
        value: 'malicious.example.com',
      });
      expect(result).toEqual(entry);
    });

    it('deletes a blocklist entry', async () => {
      const message = { message: 'Blocklist entry removed successfully', meta };
      mockApiClient.delete.mockResolvedValue({ data: message });

      const result = await deleteBlocklistEntry('e1');

      expect(mockApiClient.delete).toHaveBeenCalledWith('/threatintel/blocklist/e1');
      expect(result).toEqual(message);
    });
  });

  describe('checkIoc', () => {
    it('returns the verdict when found', async () => {
      const verdict = {
        ioc_type: 'domain',
        value: 'malicious.example.com',
        severity: 'high',
        source: 'misp',
        stix_id: 'indicator--abc',
        first_seen: 1700000000,
        expiry: null,
      };
      mockApiClient.get.mockResolvedValue({ data: verdict });

      const result = await checkIoc('domain', 'malicious.example.com');

      expect(mockApiClient.get).toHaveBeenCalledWith('/threatintel/blocklist/check', {
        params: { type: 'domain', value: 'malicious.example.com' },
      });
      expect(result).toEqual(verdict);
    });

    it('returns null on a 404 not-found response', async () => {
      mockApiClient.get.mockRejectedValue({ response: { status: 404 } });

      const result = await checkIoc('domain', 'clean.example.com');

      expect(result).toBeNull();
    });

    it('rethrows non-404 errors', async () => {
      mockApiClient.get.mockRejectedValue({ response: { status: 500 } });

      await expect(checkIoc('domain', 'clean.example.com')).rejects.toEqual({
        response: { status: 500 },
      });
    });
  });
});
