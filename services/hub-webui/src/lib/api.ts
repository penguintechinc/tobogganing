import axios, { type AxiosInstance, type AxiosError } from "axios";

// ---- Types ----

export interface User {
  id: string;
  email: string;
  name: string;
  role: "admin" | "maintainer" | "viewer";
  created_at: string;
}

export interface AuthResponse {
  token: string;
  user: User;
}

/** Envelope returned by hub-api for every response. */
export interface ApiEnvelope<T> {
  status: "success" | "error";
  data: T;
  meta?: { version: string; timestamp: string };
}

export type PolicyScope = "wireguard" | "k8s" | "both";

export interface Policy {
  id: number;
  name: string;
  description: string;
  enabled: boolean;
  action: "allow" | "deny";
  priority: number;
  scope: PolicyScope;
  direction: "inbound" | "outbound" | "both";
  domains: string[];
  ports: string[];
  protocol: "tcp" | "udp" | "icmp" | "any";
  src_cidrs: string[];
  dst_cidrs: string[];
  users: string[];
  groups: string[];
  identity_provider: string;
  created_at: string;
  updated_at: string;
}

export interface Client {
  id: string;
  name: string;
  hostname: string;
  status: "connected" | "disconnected" | "pending";
  hub_ids: string[];
  ip_address: string;
  last_seen: string;
  version: string;
}

export interface Hub {
  id: string;
  name: string;
  endpoint: string;
  status: "healthy" | "degraded" | "offline";
  connected_clients: number;
  capacity: number;
  uptime_seconds: number;
  version: string;
}

export interface IdentityProvider {
  id: string;
  name: string;
  type: "local" | "oidc" | "saml" | "scim";
  enabled: boolean;
  premium: boolean;
  config: Record<string, string>;
}

export interface AuditLogEntry {
  id: string;
  timestamp: string;
  event_type: "auth" | "policy_decision" | "admin_action" | "system";
  actor: string;
  action: string;
  target: string;
  details: string;
  result: "success" | "failure";
}

export interface DashboardStats {
  total_hubs: number;
  healthy_hubs: number;
  total_clients: number;
  connected_clients: number;
  total_policies: number;
  active_policies: number;
  active_sessions: number;
}

// ---- API Client ----

const TOKEN_KEY = "tobogganing_token";

function createApiClient(): AxiosInstance {
  const client = axios.create({
    baseURL: "/api/v1",
    headers: {
      "Content-Type": "application/json",
    },
    timeout: 15_000,
  });

  // Request interceptor: attach JWT token
  client.interceptors.request.use((config) => {
    const token = localStorage.getItem(TOKEN_KEY);
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  });

  // Response interceptor: handle 401 globally
  client.interceptors.response.use(
    (response) => response,
    (error: AxiosError) => {
      if (error.response?.status === 401) {
        localStorage.removeItem(TOKEN_KEY);
        window.location.href = "/login";
      }
      return Promise.reject(error);
    },
  );

  return client;
}

const apiClient = createApiClient();

// ---- Auth API ----

export const authApi = {
  login: async (email: string, password: string): Promise<AuthResponse> => {
    const { data } = await apiClient.post<AuthResponse>("/auth/login", {
      email,
      password,
    });
    return data;
  },

  logout: async (): Promise<void> => {
    await apiClient.post("/auth/logout");
  },

  me: async (): Promise<User> => {
    const { data } = await apiClient.get<User>("/auth/me");
    return data;
  },

  refresh: async (): Promise<AuthResponse> => {
    const { data } = await apiClient.post<AuthResponse>("/auth/refresh");
    return data;
  },
};

// ---- Policies API ----

export const policiesApi = {
  list: async (): Promise<Policy[]> => {
    const { data } = await apiClient.get<
      ApiEnvelope<{ policies: Policy[]; total: number }>
    >("/policies");
    return data.data.policies;
  },

  get: async (id: number): Promise<Policy> => {
    const { data } = await apiClient.get<ApiEnvelope<Policy>>(
      `/policies/${id}`,
    );
    return data.data;
  },

  create: async (
    policy: Omit<Policy, "id" | "created_at" | "updated_at">,
  ): Promise<Policy> => {
    const { data } = await apiClient.post<ApiEnvelope<Policy>>(
      "/policies",
      policy,
    );
    return data.data;
  },

  update: async (id: number, policy: Partial<Policy>): Promise<Policy> => {
    const { data } = await apiClient.put<ApiEnvelope<Policy>>(
      `/policies/${id}`,
      policy,
    );
    return data.data;
  },

  delete: async (id: number): Promise<void> => {
    await apiClient.delete(`/policies/${id}`);
  },
};

// ---- Clients API ----

export const clientsApi = {
  list: async (): Promise<Client[]> => {
    const { data } = await apiClient.get<Client[]>("/clients");
    return data;
  },

  get: async (id: string): Promise<Client> => {
    const { data } = await apiClient.get<Client>(`/clients/${id}`);
    return data;
  },

  delete: async (id: string): Promise<void> => {
    await apiClient.delete(`/clients/${id}`);
  },
};

// ---- Hubs API ----

export const hubsApi = {
  list: async (): Promise<Hub[]> => {
    const { data } = await apiClient.get<Hub[]>("/hubs");
    return data;
  },

  get: async (id: string): Promise<Hub> => {
    const { data } = await apiClient.get<Hub>(`/hubs/${id}`);
    return data;
  },

  create: async (hub: Omit<Hub, "id">): Promise<Hub> => {
    const { data } = await apiClient.post<Hub>("/hubs", hub);
    return data;
  },

  delete: async (id: string): Promise<void> => {
    await apiClient.delete(`/hubs/${id}`);
  },
};

// ---- Users API ----

export const usersApi = {
  list: async (): Promise<User[]> => {
    const { data } = await apiClient.get<User[]>("/users");
    return data;
  },

  create: async (
    user: Omit<User, "id" | "created_at"> & { password: string },
  ): Promise<User> => {
    const { data } = await apiClient.post<User>("/users", user);
    return data;
  },

  update: async (id: string, user: Partial<User>): Promise<User> => {
    const { data } = await apiClient.put<User>(`/users/${id}`, user);
    return data;
  },

  delete: async (id: string): Promise<void> => {
    await apiClient.delete(`/users/${id}`);
  },
};

// ---- Identity Providers API ----

export const identityApi = {
  list: async (): Promise<IdentityProvider[]> => {
    const { data } = await apiClient.get<IdentityProvider[]>("/identity");
    return data;
  },

  create: async (
    provider: Omit<IdentityProvider, "id">,
  ): Promise<IdentityProvider> => {
    const { data } = await apiClient.post<IdentityProvider>(
      "/identity",
      provider,
    );
    return data;
  },

  update: async (
    id: string,
    provider: Partial<IdentityProvider>,
  ): Promise<IdentityProvider> => {
    const { data } = await apiClient.put<IdentityProvider>(
      `/identity/${id}`,
      provider,
    );
    return data;
  },

  delete: async (id: string): Promise<void> => {
    await apiClient.delete(`/identity/${id}`);
  },
};

// ---- Audit Logs API ----

export const auditApi = {
  list: async (params?: {
    event_type?: string;
    limit?: number;
    offset?: number;
  }): Promise<AuditLogEntry[]> => {
    const { data } = await apiClient.get<AuditLogEntry[]>("/audit", {
      params,
    });
    return data;
  },
};

// ---- Dashboard API ----

export const dashboardApi = {
  stats: async (): Promise<DashboardStats> => {
    const { data } = await apiClient.get<DashboardStats>("/dashboard/stats");
    return data;
  },
};

export default apiClient;
