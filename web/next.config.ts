import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // 子專案掛在子網域根路徑，毋需 basePath
  output: "standalone",
};

export default nextConfig;
