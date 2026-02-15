import Link from "next/link"

export default function TroubleshootingPage() {
  return (
    <main className="min-h-screen bg-blue-bayoux text-pampas">
      <div className="mx-auto max-w-4xl px-4 py-10 md:px-8">
        <Link href="/" className="text-rock-blue underline hover:text-pampas">
          Back to catalog
        </Link>

        <h1 className="mt-4 font-headline text-4xl tracking-tight">Troubleshooting</h1>
        <p className="mt-2 text-pampas/75">
          Use this page if install or setup commands fail.
        </p>

        <section className="mt-8 space-y-3 rounded-2xl border border-rock-blue/25 bg-pampas/5 p-5">
          <h2 className="text-xl font-semibold">1. Check Python Version</h2>
          <pre className="rounded-xl border border-rock-blue/20 bg-black/20 p-4 text-sm overflow-x-auto">
{`python3 --version`}
          </pre>
          <p className="text-sm text-pampas/75">
            <code>agent-toolbox</code> requires Python 3.10+.
          </p>
        </section>

        <section className="mt-5 space-y-3 rounded-2xl border border-rock-blue/25 bg-pampas/5 p-5">
          <h2 className="text-xl font-semibold">2. Install pipx</h2>
          <p className="text-sm text-pampas/75">macOS/Linux</p>
          <pre className="rounded-xl border border-rock-blue/20 bg-black/20 p-4 text-sm overflow-x-auto">
{`python3 -m pip install --user pipx
python3 -m pipx ensurepath`}
          </pre>
          <p className="text-sm text-pampas/75">Windows PowerShell</p>
          <pre className="rounded-xl border border-rock-blue/20 bg-black/20 p-4 text-sm overflow-x-auto">
{`py -m pip install --user pipx
py -m pipx ensurepath`}
          </pre>
        </section>

        <section className="mt-5 space-y-3 rounded-2xl border border-rock-blue/25 bg-pampas/5 p-5">
          <h2 className="text-xl font-semibold">3. Install Agent Toolbox</h2>
          <pre className="rounded-xl border border-rock-blue/20 bg-black/20 p-4 text-sm overflow-x-auto">
{`pipx install agent-toolbox
agent-toolbox setup`}
          </pre>
        </section>

        <section className="mt-5 space-y-3 rounded-2xl border border-rock-blue/25 bg-pampas/5 p-5">
          <h2 className="text-xl font-semibold">4. Command Not Found</h2>
          <pre className="rounded-xl border border-rock-blue/20 bg-black/20 p-4 text-sm overflow-x-auto">
{`agent-toolbox doctor`}
          </pre>
          <p className="text-sm text-pampas/75">
            If command is still missing after install, restart your terminal and run{" "}
            <code>pipx ensurepath</code> again.
          </p>
        </section>

        <section className="mt-5 space-y-3 rounded-2xl border border-rock-blue/25 bg-pampas/5 p-5">
          <h2 className="text-xl font-semibold">5. Homebrew/PEP 668 Fallback</h2>
          <pre className="rounded-xl border border-rock-blue/20 bg-black/20 p-4 text-sm overflow-x-auto">
{`python3.10 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install agent-toolbox`}
          </pre>
        </section>
      </div>
    </main>
  )
}
