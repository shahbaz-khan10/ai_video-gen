import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  resolve: { tsconfigPaths: true },
  test: {
    environment: "jsdom",
    include: ["src/**/*.test.{ts,tsx}"],
    // Tests never call a real backend; this only lets `assetUrl` build absolute URLs.
    env: { NEXT_PUBLIC_API_BASE_URL: "http://localhost:8000" },
  },
});
