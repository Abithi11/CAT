import React, { createContext, useContext, useEffect, useState } from "react";

const AuthContext = createContext(null);
const STORAGE_KEY = "argus.session";

export function AuthProvider({ children }) {
  const [operator, setOperator] = useState(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) {
      try {
        setOperator(JSON.parse(raw));
      } catch {
        localStorage.removeItem(STORAGE_KEY);
      }
    }
    setReady(true);
  }, []);

  function login({ operatorId, site, tenant, role }) {
    const session = {
      operatorId,
      site,
      tenant: tenant || "default",
      role: role || "dealer",
      loggedInAt: new Date().toISOString(),
    };
    localStorage.setItem(STORAGE_KEY, JSON.stringify(session));
    setOperator(session);
  }

  function logout() {
    localStorage.removeItem(STORAGE_KEY);
    setOperator(null);
  }

  return (
    <AuthContext.Provider value={{ operator, login, logout, ready }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
