import "./globals.css";

export const metadata = { title: "Apprentice Desk", description: "Voice-assisted apprenticeship application" };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
