import { Snowflake } from "lucide-react";
import { LoginPageBuilder, type LoginResponse } from "@penguintechinc/react-libs";
import { useAuth } from "../lib/auth";

export default function Login() {
  const { loginWithToken } = useAuth();

  const handleSuccess = (response: LoginResponse) => {
    if (response.token && response.user) {
      loginWithToken(response.token, {
        id: response.user.id,
        email: response.user.email,
        name: response.user.name ?? response.user.email,
        role: (response.user.roles?.[0] as "admin" | "maintainer" | "viewer") ?? "viewer",
        created_at: new Date().toISOString(),
      });
    }
  };

  return (
    <LoginPageBuilder
      api={{ loginUrl: "/api/v1/auth/login" }}
      branding={{
        appName: "Tobogganing",
        logo: <Snowflake className="h-16 w-16 text-amber-400" />,
        tagline: "Hub Management Console",
        githubRepo: "penguintechinc/tobogganing",
      }}
      onSuccess={handleSuccess}
      showSignUp={false}
      showForgotPassword={false}
      gdpr={{ enabled: true, privacyPolicyUrl: "https://www.penguintech.io/privacy" }}
    />
  );
}
