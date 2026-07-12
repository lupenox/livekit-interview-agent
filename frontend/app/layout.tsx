import type { Metadata } from 'next';
import '@livekit/components-styles';
import './globals.css';

export const metadata: Metadata = {
  title: 'MockMate | AI Interview Practice',
  description: 'Practice behavioral and technical interviews with a real-time AI interviewer.',
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
