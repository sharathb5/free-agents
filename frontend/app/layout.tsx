import type { Metadata } from "next"
import { Fraunces, Inter } from "next/font/google"
import { ClerkProvider } from "@clerk/nextjs"
import "./globals.css"

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap",
})

const fraunces = Fraunces({
  subsets: ["latin"],
  variable: "--font-fraunces",
  display: "swap",
})

export const metadata: Metadata = {
  title: "Agent Catalog",
  description: "Installable, schema-validated agent APIs",
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en">
      <body className={`${inter.variable} ${fraunces.variable} font-ui antialiased`}>
        <ClerkProvider>
          {children}
          <div className="fixed bottom-3 right-4 text-xs text-pampas/50 flex items-center gap-3">
            <a
              href="https://github.com/sharathb5"
              target="_blank"
              rel="noopener noreferrer"
              className="hover:text-pampas/80 transition-colors"
            >
              GitHub
            </a>
            <a
              href="https://x.com/_sharathb"
              target="_blank"
              rel="noopener noreferrer"
              className="hover:text-pampas/80 transition-colors"
            >
              X
            </a>
          </div>
        </ClerkProvider>
      </body>
    </html>
  )
}
