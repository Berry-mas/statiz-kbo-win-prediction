import { ImageResponse } from "next/og";

export const alt = "Y-wins KBO Forecast dashboard preview";
export const size = {
  width: 1200,
  height: 630,
};
export const contentType = "image/png";

export default function Image() {
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          justifyContent: "space-between",
          padding: "54px 62px",
          background: "linear-gradient(135deg, #eef2ed 0%, #ffffff 46%, #f7eddb 100%)",
          color: "#171a18",
          fontFamily: "Inter, Arial, sans-serif",
        }}
      >
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: "14px",
              color: "#0d7a5f",
              fontSize: 30,
              fontWeight: 800,
              letterSpacing: 0,
            }}
          >
            <span
              style={{
                width: 44,
                height: 44,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                borderRadius: 8,
                background: "#171a18",
                color: "#ffffff",
              }}
            >
              Y
            </span>
            Y-wins KBO Forecast
          </div>
          <div style={{ color: "#65716b", fontSize: 24, fontWeight: 700 }}>Submitted KBO game forecasts</div>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: "20px" }}>
          <div style={{ fontSize: 78, fontWeight: 900, lineHeight: 0.96, letterSpacing: 0 }}>
            KBO win probability dashboard
          </div>
          <div style={{ width: 800, color: "#65716b", fontSize: 32, fontWeight: 700, lineHeight: 1.25 }}>
            Daily submitted games, finalized ledger, and recent model performance in one public view.
          </div>
        </div>

        <div style={{ display: "flex", gap: "18px" }}>
          <div
            style={{
              display: "flex",
              alignItems: "center",
              padding: "14px 20px",
              borderRadius: 999,
              background: "#dcefe7",
              color: "#0d7a5f",
              fontSize: 26,
              fontWeight: 850,
            }}
          >
            Submitted games
          </div>
          <div
            style={{
              display: "flex",
              alignItems: "center",
              padding: "14px 20px",
              borderRadius: 999,
              background: "#dce9ef",
              color: "#2e607d",
              fontSize: 26,
              fontWeight: 850,
            }}
          >
            Finalized ledger
          </div>
          <div
            style={{
              display: "flex",
              alignItems: "center",
              padding: "14px 20px",
              borderRadius: 999,
              background: "#f4e7cf",
              color: "#9a6712",
              fontSize: 26,
              fontWeight: 850,
            }}
          >
            Model metrics
          </div>
        </div>
      </div>
    ),
    size,
  );
}
