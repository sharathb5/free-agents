#!/usr/bin/env python3
"""Test all 5 agents via API using pytest TestClient."""
import os
import json
from fastapi.testclient import TestClient

# Import app
from app.main import app

def test_all_agents():
    """Test all 5 agents with their expected input schemas."""
    
    agents_to_test = [
        {
            "preset": "summarizer",
            "input": {"text": "This is a test paragraph that should be summarized."},
            "description": "Text summarization"
        },
        {
            "preset": "classifier",
            "input": {
                "items": [
                    {"id": "1", "content": "Reset my password"},
                    {"id": "2", "content": "Pricing question"}
                ],
                "categories": ["support", "sales", "other"]
            },
            "description": "Item classification"
        },
        {
            "preset": "meeting_notes",
            "input": {
                "transcript": "Today we decided to launch v1 next week and assign Alice to write the README."
            },
            "description": "Meeting notes extraction"
        },
        {
            "preset": "extractor",
            "input": {
                "text": "Acme Corp signed a contract on Jan 1, 2025 with a value of $10,000.",
                "schema": {
                    "customer_name": "Name of the customer",
                    "contract_date": "Date the contract was signed",
                    "contract_value": "Monetary value of the contract"
                }
            },
            "description": "Structured data extraction"
        },
        {
            "preset": "triage",
            "input": {
                "email_content": "Urgent: our production server is down.",
                "mailbox_context": "On-call support mailbox"
            },
            "description": "Email triage"
        }
    ]
    
    for agent in agents_to_test:
        preset = agent["preset"]
        print(f"\n{'='*60}")
        print(f"Testing: {preset} - {agent['description']}")
        print(f"{'='*60}")
        
        # Set environment
        os.environ["AGENT_PRESET"] = preset
        os.environ["PROVIDER"] = "stub"
        os.environ["AUTH_TOKEN"] = ""
        
        # Create fresh client (app reloads preset from env)
        client = TestClient(app)
        
        # Test /health
        print("\n→ GET /health")
        resp = client.get("/health")
        assert resp.status_code == 200, f"Health check failed: {resp.status_code}"
        health_data = resp.json()
        assert health_data["agent"] == preset
        print(f"✓ Health OK: agent={health_data['agent']}, version={health_data['version']}")
        
        # Test /schema
        print("\n→ GET /schema")
        resp = client.get("/schema")
        assert resp.status_code == 200, f"Schema endpoint failed: {resp.status_code}"
        schema_data = resp.json()
        assert schema_data["agent"] == preset
        assert "input_schema" in schema_data
        assert "output_schema" in schema_data
        print(f"✓ Schema OK: agent={schema_data['agent']}, primitive={schema_data['primitive']}")
        
        # Test /invoke
        print("\n→ POST /invoke")
        resp = client.post("/invoke", json={"input": agent["input"]})
        assert resp.status_code == 200, f"Invoke failed: {resp.status_code} - {resp.text}"
        invoke_data = resp.json()
        assert "output" in invoke_data
        assert "meta" in invoke_data
        assert invoke_data["meta"]["agent"] == preset
        print(f"✓ Invoke OK: agent={invoke_data['meta']['agent']}, latency_ms={invoke_data['meta']['latency_ms']:.2f}")
        print(f"  Output keys: {list(invoke_data['output'].keys())}")
    
    print(f"\n{'='*60}")
    print("All 5 agents tested successfully!")
    print(f"{'='*60}")

if __name__ == "__main__":
    test_all_agents()
