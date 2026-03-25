import {
  Fingerprint,
  Users,
  Globe,
  KeyRound,
  BookUser,
  Crown,
  ToggleLeft,
  ToggleRight,
  Settings,
} from "lucide-react";
import clsx from "clsx";
import type { IdentityProvider } from "../lib/api";

const mockProviders: IdentityProvider[] = [
  {
    id: "idp-local",
    name: "Local Users",
    type: "local",
    enabled: true,
    premium: false,
    config: {
      password_policy: "strong",
      mfa_enabled: "false",
    },
  },
  {
    id: "idp-oidc",
    name: "Azure AD (OIDC)",
    type: "oidc",
    enabled: false,
    premium: true,
    config: {
      issuer: "https://login.microsoftonline.com/tenant-id",
      client_id: "app-client-id",
      redirect_uri: "https://hub.example.com/auth/callback",
    },
  },
  {
    id: "idp-saml",
    name: "Okta (SAML)",
    type: "saml",
    enabled: false,
    premium: true,
    config: {
      entity_id: "https://hub.example.com",
      sso_url: "https://company.okta.com/sso/saml",
      certificate: "configured",
    },
  },
  {
    id: "idp-scim",
    name: "SCIM Provisioning",
    type: "scim",
    enabled: false,
    premium: true,
    config: {
      endpoint: "https://hub.example.com/scim/v2",
      bearer_token: "configured",
    },
  },
];

const typeConfig = {
  local: {
    icon: Users,
    label: "Local",
    description: "Built-in user management with email/password authentication",
  },
  oidc: {
    icon: Globe,
    label: "OIDC",
    description:
      "OpenID Connect for SSO with Azure AD, Google Workspace, and more",
  },
  saml: {
    icon: KeyRound,
    label: "SAML",
    description:
      "SAML 2.0 for enterprise SSO with Okta, OneLogin, PingIdentity",
  },
  scim: {
    icon: BookUser,
    label: "SCIM",
    description:
      "System for Cross-domain Identity Management for automated user provisioning",
  },
};

export default function IdentityProviders() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-text-gold">
          Identity Providers
        </h1>
        <p className="mt-1 text-sm text-text-secondary">
          Configure authentication sources and user provisioning
        </p>
      </div>

      {/* Provider cards */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {mockProviders.map((provider) => (
          <ProviderCard key={provider.id} provider={provider} />
        ))}
      </div>

      {/* License info */}
      <div className="rounded-xl border border-accent/30 bg-accent/5 p-5">
        <div className="flex items-start gap-3">
          <Crown className="mt-0.5 h-5 w-5 text-accent" />
          <div>
            <h3 className="text-sm font-semibold text-text-gold">
              Premium Feature
            </h3>
            <p className="mt-1 text-sm text-text-secondary">
              OIDC, SAML, and SCIM integrations require a premium license.
              Local user management is available on all plans. Contact{" "}
              <a
                href="mailto:sales@penguintech.io"
                className="text-accent underline hover:text-accent-hover"
              >
                sales@penguintech.io
              </a>{" "}
              to upgrade your license.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}

function ProviderCard({ provider }: { provider: IdentityProvider }) {
  const config = typeConfig[provider.type];

  return (
    <div
      className={clsx(
        "rounded-xl border bg-bg-secondary p-6 transition-colors",
        provider.enabled ? "border-accent/30" : "border-border",
      )}
    >
      <div className="flex items-start justify-between">
        <div className="flex items-start gap-3">
          <div
            className={clsx(
              "rounded-lg p-2.5",
              provider.enabled ? "bg-accent/10" : "bg-bg-tertiary",
            )}
          >
            <config.icon
              className={clsx(
                "h-6 w-6",
                provider.enabled ? "text-accent" : "text-text-muted",
              )}
            />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h3 className="text-base font-semibold text-text-primary">
                {provider.name}
              </h3>
              {provider.premium && (
                <span className="flex items-center gap-1 rounded-full bg-accent/15 px-2 py-0.5 text-xs font-medium text-text-gold">
                  <Crown className="h-3 w-3" />
                  Premium
                </span>
              )}
            </div>
            <span className="mt-0.5 inline-block rounded bg-bg-tertiary px-2 py-0.5 text-xs text-text-muted">
              {config.label}
            </span>
          </div>
        </div>

        <button
          className="text-text-secondary hover:text-text-primary"
          title={provider.enabled ? "Disable" : "Enable"}
        >
          {provider.enabled ? (
            <ToggleRight className="h-6 w-6 text-accent" />
          ) : (
            <ToggleLeft className="h-6 w-6" />
          )}
        </button>
      </div>

      <p className="mt-3 text-sm text-text-secondary">{config.description}</p>

      {/* Config summary */}
      {Object.keys(provider.config).length > 0 && (
        <div className="mt-4 rounded-lg bg-bg-primary p-3">
          <div className="space-y-1.5">
            {Object.entries(provider.config).map(([key, value]) => (
              <div key={key} className="flex items-center justify-between">
                <span className="text-xs text-text-muted">
                  {key.replace(/_/g, " ")}
                </span>
                <span className="max-w-[200px] truncate text-xs text-text-secondary">
                  {key.includes("token") || key.includes("secret")
                    ? "********"
                    : value}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="mt-4">
        <button
          className={clsx(
            "flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm transition-colors",
            provider.premium && !provider.enabled
              ? "border border-border text-text-muted cursor-not-allowed"
              : "border border-border text-text-secondary hover:bg-bg-tertiary hover:text-text-primary",
          )}
          disabled={provider.premium && !provider.enabled}
        >
          <Settings className="h-3.5 w-3.5" />
          Configure
        </button>
      </div>
    </div>
  );
}
