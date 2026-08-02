import { ImageResponse } from "next/og";

export const alt = "Ruan's 中職數據實驗室";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

export default function OpenGraphImage() {
  return new ImageResponse(<div style={{ background: "#0a2540", color: "#f5f7fa", width: "100%", height: "100%", display: "flex", alignItems: "center", padding: 80, fontFamily: "sans-serif" }}><div style={{ display: "flex", flexDirection: "column" }}><div style={{ display: "flex", color: "#d12638", fontSize: 36, fontWeight: 700 }}>RUAN&apos;S <span style={{ color: "#5c95e2" }}>CPBL</span> LAB</div><div style={{ marginTop: 36, fontSize: 72, fontWeight: 800 }}>中職數據實驗室</div><div style={{ marginTop: 24, color: "#a1b2c6", fontSize: 32 }}>從最近賽事到下一場對戰，用可追溯的數據看懂中職。</div></div></div>, size);
}
