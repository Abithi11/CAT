import React from "react";
import { Routes, Route, Navigate, useLocation } from "react-router-dom";
import { AuthProvider, useAuth } from "@/context/AuthContext";
import { Layout } from "@/components/Layout";
import Login from "@/pages/Login";
import Home from "@/pages/Home";
import Scan from "@/pages/Scan";
import Chat from "@/pages/Chat";
import QueryBuilder from "@/pages/QueryBuilder";
import Reports from "@/pages/Reports";
import Forecast from "@/pages/Forecast";
import Health from "@/pages/Health";
import Alerts from "@/pages/Alerts";

function ProtectedRoute({ children }) {
  const { operator, ready } = useAuth();
  const location = useLocation();

  if (!ready) return null;
  if (!operator) {
    return <Navigate to="/login" state={{ from: location.pathname }} replace />;
  }
  return <Layout>{children}</Layout>;
}

function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/home" element={<ProtectedRoute><Home /></ProtectedRoute>} />
      <Route path="/scan" element={<ProtectedRoute><Scan /></ProtectedRoute>} />
      <Route path="/chat" element={<ProtectedRoute><Chat /></ProtectedRoute>} />
      <Route path="/query" element={<ProtectedRoute><QueryBuilder /></ProtectedRoute>} />
      <Route path="/reports" element={<ProtectedRoute><Reports /></ProtectedRoute>} />
      <Route path="/forecast" element={<ProtectedRoute><Forecast /></ProtectedRoute>} />
      <Route path="/health" element={<ProtectedRoute><Health /></ProtectedRoute>} />
      <Route path="/alerts" element={<ProtectedRoute><Alerts /></ProtectedRoute>} />
      <Route path="/" element={<Navigate to="/home" replace />} />
      <Route path="*" element={<Navigate to="/home" replace />} />
    </Routes>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <AppRoutes />
    </AuthProvider>
  );
}
