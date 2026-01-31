# Agent Catalog Frontend

A modern, developer-facing marketplace UI for browsing and installing AI agents.

## Tech Stack

- **Next.js 14** (App Router)
- **TypeScript**
- **Tailwind CSS**
- **shadcn/ui** components
- **Radix UI** primitives

## Getting Started

### Install Dependencies

```bash
npm install
```

### Run Development Server

```bash
npm run dev
```

Open [http://localhost:3000](http://localhost:3000) in your browser.

### Build for Production

```bash
npm run build
npm start
```

## Features

- **Marketplace Grid**: Browse agents in a responsive card grid
- **Search**: Filter agents by name, description, or tags
- **Primitive Filters**: Filter by agent type (Transform, Extract, Classify)
- **Detail Modal**: Click any agent card to view detailed information
- **Tabbed Details**: Overview, Install, API, and Schema tabs
- **Copy to Clipboard**: One-click copy for install commands, API snippets, and schemas
- **Toast Notifications**: Visual feedback for copy actions

## Color Palette

- **Blue Bayoux** (#496677): Primary background accents
- **Rock Blue** (#9FB2CD): Secondary surfaces
- **Pampas** (#F0EDE8): Main page background
- **Olive Green** (#ABAC5A): Accent / success / "Install" buttons
- **Kilamanjaro** (#271203): Primary text / dark surfaces

## Project Structure

```
frontend/
├── app/
│   ├── layout.tsx          # Root layout
│   ├── page.tsx            # Main marketplace page
│   └── globals.css         # Global styles
├── components/
│   ├── ui/                 # shadcn/ui components
│   ├── AgentCard.tsx       # Agent card component
│   ├── AgentDetailModal.tsx # Detail modal with tabs
│   └── CodeBlock.tsx       # Code block with copy
├── lib/
│   ├── agents.ts           # Mock agent data
│   └── utils.ts            # Utility functions
└── package.json
```

## Mock Data

The app uses mock data defined in `lib/agents.ts`. This includes:
- 5 real agents: summarizer, meeting_notes, extractor, classifier, triage
- 4 dummy agents: sentiment_analyzer, entity_extractor, text_translator, content_moderator

Each agent includes:
- Basic info (name, description, primitive type)
- Install commands (local and Docker)
- API examples (curl, input/output)
- JSON schemas (input and output)

## Notes

- This is a frontend-only implementation
- No backend integration yet
- All data is mocked in code
- Routing is kept simple (single page) to avoid complexity
- UI is **dark-mode by default** and uses **Fraunces** (headlines) + **Inter** (UI/body)
