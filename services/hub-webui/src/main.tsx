import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AppConsoleVersion, type AppConsoleVersionProps } from "@penguintechinc/react-libs";

// Cast to FC since the library returns ReactNode (valid JSX) but is typed as ReactNode not JSX.Element
const AppConsoleVersionFC = AppConsoleVersion as React.FC<AppConsoleVersionProps>;
import { AuthProvider } from "./lib/auth";
import App from "./App";
import "./app.css";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <AppConsoleVersionFC
      appName="Tobogganing Hub WebUI"
      webuiVersion="2.0.0"
      styleConfig={{ primaryColor: "#fbbf24" }}
    />
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AuthProvider>
          <App />
        </AuthProvider>
      </BrowserRouter>
    </QueryClientProvider>
  </React.StrictMode>,
);
