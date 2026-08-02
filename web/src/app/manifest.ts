import type { MetadataRoute } from "next";

export default function manifest(): MetadataRoute.Manifest {
  return { name: "Ruan's CPBL Lab", short_name: "CPBL Lab", start_url: "/", display: "standalone", background_color: "#f5f7fa", theme_color: "#f5f7fa", icons: [{ src: "/icon.svg", type: "image/svg+xml", sizes: "any" }] };
}
