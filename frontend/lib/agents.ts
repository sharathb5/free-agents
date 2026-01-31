export type Primitive = "transform" | "extract" | "classify"

export interface Agent {
  id: string
  name: string
  description: string
  primitive: Primitive
  tags: string[]
  installCommand: string
  dockerCommand: string
  exampleInvoke: {
    curl: string
    input: Record<string, any>
    output: Record<string, any>
  }
  inputSchema: Record<string, any>
  outputSchema: Record<string, any>
  useCases?: string[]
}

export const agents: Agent[] = [
  {
    id: "summarizer",
    name: "Text Summarizer",
    description: "Summarize long text into a concise form with key bullet points.",
    primitive: "transform",
    tags: ["text", "summarization", "nlp"],
    installCommand: "AGENT_PRESET=summarizer make run",
    dockerCommand: "make docker-up AGENT=summarizer",
    exampleInvoke: {
      curl: `curl -X POST http://localhost:4280/invoke \\
  -H "Content-Type: application/json" \\
  -d '{"input": {"text": "Some long text to summarize."}}'`,
      input: {
        text: "Some long text to summarize."
      },
      output: {
        summary: "A concise summary of the text.",
        bullets: ["Key point 1", "Key point 2", "Key point 3"]
      }
    },
    inputSchema: {
      type: "object",
      required: ["text"],
      properties: {
        text: {
          type: "string",
          title: "Text to summarize"
        }
      }
    },
    outputSchema: {
      type: "object",
      required: ["summary", "bullets"],
      properties: {
        summary: {
          type: "string",
          title: "Summary of the input text"
        },
        bullets: {
          type: "array",
          items: {
            type: "string",
            title: "Summary bullet point"
          }
        }
      }
    },
    useCases: [
      "Summarize long articles or documents",
      "Extract key points from meeting transcripts",
      "Create executive summaries from detailed reports"
    ]
  },
  {
    id: "meeting_notes",
    name: "Meeting Notes Extractor",
    description: "Extract structured notes, decisions, and action items from a meeting transcript.",
    primitive: "extract",
    tags: ["meetings", "extraction", "productivity"],
    installCommand: "AGENT_PRESET=meeting_notes make run",
    dockerCommand: "make docker-up AGENT=meeting_notes",
    exampleInvoke: {
      curl: `curl -X POST http://localhost:4280/invoke \\
  -H "Content-Type: application/json" \\
  -d '{"input": {"transcript": "Meeting transcript text here..."}}'`,
      input: {
        transcript: "Meeting transcript text here..."
      },
      output: {
        summary: "High-level summary of the meeting",
        decisions: ["Decision 1", "Decision 2"],
        action_items: [
          {
            owner: "John Doe",
            task: "Follow up on action item",
            deadline: "2024-01-15"
          }
        ]
      }
    },
    inputSchema: {
      type: "object",
      required: ["transcript"],
      properties: {
        transcript: {
          type: "string",
          title: "Full meeting transcript"
        }
      }
    },
    outputSchema: {
      type: "object",
      required: ["summary", "decisions", "action_items"],
      properties: {
        summary: {
          type: "string",
          title: "High-level summary of the meeting"
        },
        decisions: {
          type: "array",
          items: {
            type: "string"
          },
          title: "Key decisions made in the meeting"
        },
        action_items: {
          type: "array",
          items: {
            type: "object",
            properties: {
              owner: { type: "string" },
              task: { type: "string" },
              deadline: { type: "string" }
            },
            required: ["owner", "task", "deadline"]
          },
          title: "Action items with owner, task, and deadline"
        }
      }
    },
    useCases: [
      "Automatically extract action items from team meetings",
      "Generate structured meeting summaries",
      "Track decisions and follow-ups from calls"
    ]
  },
  {
    id: "extractor",
    name: "Generic Extractor",
    description: "Extract arbitrary structured data from text given a schema description.",
    primitive: "extract",
    tags: ["extraction", "schema", "flexible"],
    installCommand: "AGENT_PRESET=extractor make run",
    dockerCommand: "make docker-up AGENT=extractor",
    exampleInvoke: {
      curl: `curl -X POST http://localhost:4280/invoke \\
  -H "Content-Type: application/json" \\
  -d '{"input": {"text": "Source text", "schema": {"name": "Person name", "email": "Email address"}}}'`,
      input: {
        text: "Source text",
        schema: {
          name: "Person name",
          email: "Email address"
        }
      },
      output: {
        data: {
          name: "John Doe",
          email: "john@example.com"
        },
        confidence: 0.95
      }
    },
    inputSchema: {
      type: "object",
      required: ["text", "schema"],
      properties: {
        text: {
          type: "string",
          title: "Source text to extract data from"
        },
        schema: {
          type: "object",
          additionalProperties: {
            type: "string"
          },
          title: "Mapping of field_name to human-readable description"
        }
      }
    },
    outputSchema: {
      type: "object",
      required: ["data", "confidence"],
      properties: {
        data: {
          type: "object",
          title: "Extracted data keyed by field_name",
          additionalProperties: true
        },
        confidence: {
          type: "number",
          minimum: 0,
          maximum: 1,
          title: "Overall confidence score in [0,1]"
        }
      }
    },
    useCases: [
      "Extract structured data from unstructured text",
      "Parse contact information from documents",
      "Custom field extraction with flexible schemas"
    ]
  },
  {
    id: "classifier",
    name: "Generic Classifier",
    description: "Classify items into categories with confidence scores.",
    primitive: "classify",
    tags: ["classification", "categorization", "ml"],
    installCommand: "AGENT_PRESET=classifier make run",
    dockerCommand: "make docker-up AGENT=classifier",
    exampleInvoke: {
      curl: `curl -X POST http://localhost:4280/invoke \\
  -H "Content-Type: application/json" \\
  -d '{"input": {"items": [{"id": "1", "content": "Reset my password"}], "categories": ["support", "sales", "other"]}}'`,
      input: {
        items: [
          { id: "1", content: "Reset my password" },
          { id: "2", content: "Pricing question" }
        ],
        categories: ["support", "sales", "other"]
      },
      output: {
        classifications: [
          {
            item_id: "1",
            category: "support",
            confidence: 0.95
          },
          {
            item_id: "2",
            category: "sales",
            confidence: 0.88
          }
        ]
      }
    },
    inputSchema: {
      type: "object",
      required: ["items"],
      properties: {
        items: {
          type: "array",
          items: {
            type: "object",
            properties: {
              id: { type: "string" },
              content: { type: "string" }
            },
            required: ["id", "content"]
          }
        },
        categories: {
          type: "array",
          items: {
            type: "string"
          }
        }
      }
    },
    outputSchema: {
      type: "object",
      required: ["classifications"],
      properties: {
        classifications: {
          type: "array",
          items: {
            type: "object",
            properties: {
              item_id: { type: "string" },
              category: { type: "string" },
              confidence: {
                type: "number",
                minimum: 0,
                maximum: 1
              }
            },
            required: ["item_id", "category", "confidence"]
          }
        }
      }
    },
    useCases: [
      "Categorize support tickets automatically",
      "Route content to appropriate teams",
      "Tag and organize large datasets"
    ]
  },
  {
    id: "triage",
    name: "Email Triage Assistant",
    description: "Triage incoming emails into categories and priorities with suggested responses.",
    primitive: "classify",
    tags: ["email", "triage", "automation"],
    installCommand: "AGENT_PRESET=triage make run",
    dockerCommand: "make docker-up AGENT=triage",
    exampleInvoke: {
      curl: `curl -X POST http://localhost:4280/invoke \\
  -H "Content-Type: application/json" \\
  -d '{"input": {"email_content": "Email body", "mailbox_context": "Context info"}}'`,
      input: {
        email_content: "Email body",
        mailbox_context: "Context info"
      },
      output: {
        category: "support",
        priority: "high",
        should_escalate: true,
        draft_response: "Thank you for your email. We'll look into this..."
      }
    },
    inputSchema: {
      type: "object",
      required: ["email_content", "mailbox_context"],
      properties: {
        email_content: {
          type: "string",
          title: "Raw email body text"
        },
        mailbox_context: {
          type: "string",
          title: "Additional context about the mailbox or user"
        }
      }
    },
    outputSchema: {
      type: "object",
      required: ["category", "priority", "should_escalate", "draft_response"],
      properties: {
        category: {
          type: "string"
        },
        priority: {
          type: "string"
        },
        should_escalate: {
          type: "boolean"
        },
        draft_response: {
          type: "string"
        }
      }
    },
    useCases: [
      "Automatically triage incoming emails",
      "Prioritize urgent messages",
      "Generate draft responses for common inquiries"
    ]
  }
]
