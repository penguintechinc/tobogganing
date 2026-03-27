import { Routes, Route, Navigate } from "react-router-dom";
import { useAuth, ProtectedRoute } from "./lib/auth";
import Layout from "./components/Layout";
import Login from "./pages/Login";
import Dashboard from "./pages/Dashboard";
import PolicyManagement from "./pages/PolicyManagement";
import ClientManagement from "./pages/ClientManagement";
import HubManagement from "./pages/HubManagement";
import UserManagement from "./pages/UserManagement";
import IdentityProviders from "./pages/IdentityProviders";
import Settings from "./pages/Settings";
import AuditLogs from "./pages/AuditLogs";

function App() {
  const { user } = useAuth();

  if (!user) {
    return (
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    );
  }

  return (
    <Layout>
      <Routes>
        <Route path="/" element={<ProtectedRoute><Dashboard /></ProtectedRoute>} />
        <Route path="/policies" element={<ProtectedRoute><PolicyManagement /></ProtectedRoute>} />
        <Route path="/clients" element={<ProtectedRoute><ClientManagement /></ProtectedRoute>} />
        <Route path="/hubs" element={<ProtectedRoute><HubManagement /></ProtectedRoute>} />
        <Route path="/users" element={<ProtectedRoute><UserManagement /></ProtectedRoute>} />
        <Route path="/identity" element={<ProtectedRoute><IdentityProviders /></ProtectedRoute>} />
        <Route path="/settings" element={<ProtectedRoute><Settings /></ProtectedRoute>} />
        <Route path="/audit" element={<ProtectedRoute><AuditLogs /></ProtectedRoute>} />
        <Route path="/login" element={<Navigate to="/" replace />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Layout>
  );
}

export default App;
