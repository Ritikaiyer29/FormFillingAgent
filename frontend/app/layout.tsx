import "./globals.css";

export const metadata = { title: "Form Filling Agent", description: "Voice-assisted form filling" };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
