import { ImageResponse } from "next/og";

export const alt = "Angmoo - AI 둥지";
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
          alignItems: "center",
          background: "#f7faf6",
          display: "flex",
          height: "100%",
          justifyContent: "center",
          width: "100%",
        }}
      >
        <div
          style={{
            alignItems: "center",
            background: "#ffffff",
            border: "2px solid #e4e8de",
            borderRadius: 56,
            display: "flex",
            height: 360,
            justifyContent: "center",
            width: 360,
          }}
        >
          <AngmooLogo />
        </div>
      </div>
    ),
    size,
  );
}

function AngmooLogo() {
  return (
    <svg
      aria-label="Angmoo golden cherry parrot logo"
      height={260}
      viewBox="0 0 64 64"
      width={260}
      xmlns="http://www.w3.org/2000/svg"
    >
      <defs>
        <linearGradient id="body" x1="0.25" x2="1.03" y1="0.02" y2="0.98">
          <stop stopColor="#fff45c" />
          <stop offset="0.56" stopColor="#f4df28" />
          <stop offset="1" stopColor="#d7bd16" />
        </linearGradient>
        <linearGradient id="face" x1="-0.1" x2="0.75" y1="-0.07" y2="1.19">
          <stop stopColor="#ff5a32" />
          <stop offset="0.36" stopColor="#ff6b6b" />
          <stop offset="1" stopColor="#ef9a74" />
        </linearGradient>
        <linearGradient id="wing" x1="0.24" x2="1.05" y1="-0.02" y2="1.04">
          <stop stopColor="#fff260" />
          <stop offset="1" stopColor="#e6c91f" />
        </linearGradient>
        <linearGradient id="beak" x1="0.19" x2="0.84" y1="0" y2="1">
          <stop stopColor="#f4ddad" />
          <stop offset="1" stopColor="#d8a640" />
        </linearGradient>
      </defs>
      <path d="m34,55c10,0 19,-3 22,-8c2,-4 0,-7 -4,-6l-16,4l-2,10z" fill="#e5c91e" />
      <path d="m28,13c10,0 16,9 16,22l0,13c0,6 -5,10 -11,10l-5,0c-10,0 -16,-9 -16,-23c0,-12 6,-22 16,-22z" fill="url(#body)" />
      <path d="m15.45,20.84c4.74,-9.28 13.16,-9.54 20,-2.31c6.84,7.23 -6.93,22.33 -5.72,19.57c1.21,-2.76 7.67,-3.2 -6.56,1.28c-14.23,4.48 -12.46,-9.27 -7.72,-18.55z" fill="url(#face)" />
      <path d="m18.25,17c5.5,-7.13 17.25,-0.75 15.75,1.5c-1.5,2.25 -10.13,0.37 -16.25,2c-6.13,1.63 0.38,2.13 -0.62,1.13c-1,-1 -4.37,2.5 1.13,-4.63z" fill="#ff5a32" />
      <path d="m37.75,29.75c7,3 11,12 10,27c-6,0 -13,-3 -17,-10c-3,-5 -3,-11 0,-15c2,-2 4,-3 7,-2z" fill="#d9bf19" />
      <path d="m41,30c7,3 10,11 9,25c-5,0 -11,-3 -15,-9c-3,-5 -3,-10 0,-14c2,-2 3,-3 6,-2z" fill="url(#wing)" />
      <path d="m18,21c-7,0 -12,4 -13,9c-1,4 2,5 7,3l5,-3c5,-2 7,-8 1,-9z" fill="url(#beak)" />
      <path d="m16,25c-7,1 -11,5 -11,9c4,0 8,-1 11,-5l0,-4z" fill="#e7bd54" />
      <circle cx="26" cy="20.88" fill="#f7ead8" r="6" />
      <circle cx="26" cy="21" fill="#1f2330" r="3.1" />
      <circle cx="27.1" cy="19.7" fill="#ffffff" r="1" />
      <path d="m20,57l24,0" stroke="#c7933d" strokeLinecap="round" strokeWidth="4" />
      <path d="m27,52l0,6m10,-6l0,6" stroke="#c7933d" strokeLinecap="round" strokeWidth="3" />
    </svg>
  );
}
