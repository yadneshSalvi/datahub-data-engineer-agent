import { createContext, useContext, useEffect, useMemo, useState } from "react";

type Theme = "dark" | "light";
interface ThemeContextValue { theme: Theme; toggleTheme: () => void }

const ThemeContext = createContext<ThemeContextValue | null>(null);

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [theme, setTheme] = useState<Theme>(() => localStorage.getItem("oncall-theme-v1") === "light" ? "light" : "dark");
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem("oncall-theme-v1", theme);
  }, [theme]);
  const value = useMemo(() => ({ theme, toggleTheme: () => setTheme((current) => current === "dark" ? "light" : "dark") }), [theme]);
  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme(): ThemeContextValue {
  const value = useContext(ThemeContext);
  if (!value) throw new Error("useTheme must be used within ThemeProvider");
  return value;
}
