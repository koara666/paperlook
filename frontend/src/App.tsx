import { useEffect } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { useSettings } from "./api/hooks";
import { AppShell } from "./components/layout/AppShell";
import { applyTheme } from "./lib/theme";
import LibraryPage from "./pages/LibraryPage";
import PaperPage from "./pages/PaperPage";
import SettingsPage from "./pages/SettingsPage";
import TodayPage from "./pages/TodayPage";

export default function App() {
  const settings = useSettings();
  const theme = settings.data?.reading.theme;
  useEffect(() => {
    if (theme) applyTheme(theme);
  }, [theme]);

  return (
    <AppShell>
      <Routes>
        <Route path="/" element={<TodayPage />} />
        <Route path="/library" element={<LibraryPage />} />
        <Route path="/paper/:id" element={<PaperPage />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </AppShell>
  );
}
