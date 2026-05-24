import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import LoginPage from "./pages/LoginPage";
import AppLayout from "./components/AppLayout";
import RequireAuth from "./components/RequireAuth";
import DashboardPage from "./pages/DashboardPage";
import GasSourcesPage from "./pages/GasSourcesPage";
import StationsPage from "./pages/StationsPage";
import GCsPage from "./pages/GCsPage";
import ReconciliationPage from "./pages/ReconciliationPage";
import AlertsPage from "./pages/AlertsPage";
import UsersPage from "./pages/UsersPage";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route element={<RequireAuth />}>
          <Route element={<AppLayout />}>
            <Route path="/" element={<Navigate to="/dashboard" replace />} />
            <Route path="/dashboard" element={<DashboardPage />} />
            <Route path="/gas-sources" element={<GasSourcesPage />} />
            <Route path="/stations" element={<StationsPage />} />
            <Route path="/gcs" element={<GCsPage />} />
            <Route path="/reconciliation" element={<ReconciliationPage />} />
            <Route path="/alerts" element={<AlertsPage />} />
            <Route path="/users" element={<UsersPage />} />
          </Route>
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
