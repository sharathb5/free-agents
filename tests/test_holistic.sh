#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_DIR="$(dirname "$SCRIPT_DIR")"
cd "$BASE_DIR"

echo "Holistic Test Suite"
echo "======================"
echo ""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

PASSED=0
FAILED=0

check() {
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✓${NC} $1"
        ((PASSED++))
        return 0
    else
        echo -e "${RED}✗${NC} $1"
        ((FAILED++))
        return 1
    fi
}

# 1. Backend Tests
echo "1.  Backend Tests (pytest)"
echo "---------------------------"
if [ -d ".venv" ]; then
    source .venv/bin/activate
    python -m pytest -q --tb=short 2>&1 | tail -5
    check "Backend tests pass"
else
    echo -e "${YELLOW}⚠${NC} .venv not found, skipping pytest (run 'make install' first)"
fi
echo ""

# 2. Makefile Commands
echo "2.  Makefile Commands"
echo "----------------------"
if command -v make &> /dev/null; then
    grep -q "AGENT ?= summarizer" Makefile; check "Makefile has AGENT default"
    grep -q "^install:" Makefile; check "Makefile has install target"
    grep -q "^run:" Makefile; check "Makefile has run target"
    grep -q "^test:" Makefile; check "Makefile has test target"
    grep -q "^docker-up:" Makefile; check "Makefile has docker-up target"
    grep -q "port 4280" Makefile; check "Makefile uses port 4280"
else
    echo -e "${YELLOW}⚠${NC} make not found, skipping Makefile checks"
fi
echo ""

# 3. Preset Files
echo "3.  Preset Files"
echo "-----------------"
PRESETS=("summarizer" "classifier" "extractor" "meeting_notes" "triage")
for preset in "${PRESETS[@]}"; do
    if [ -f "app/presets/${preset}.yaml" ]; then
        check "Preset ${preset}.yaml exists (app/presets)"
    else
        echo -e "${RED}✗${NC} Preset ${preset}.yaml missing (app/presets)"
        ((FAILED++))
    fi
done
echo ""

# 4. Frontend Structure
echo "4.  Frontend Structure"
echo "----------------------"
if [ -d "frontend" ]; then
    [ -f "frontend/package.json" ]; check "Frontend package.json exists"
    [ -f "frontend/app/page.tsx" ]; check "Frontend page.tsx exists"
    [ -f "frontend/components/AgentDetailModal.tsx" ]; check "AgentDetailModal.tsx exists"

    if grep -q "If you haven.*already.*clone the repo" frontend/components/AgentDetailModal.tsx 2>/dev/null; then
        check "Agent modal references global setup (not repeating it)"
    else
        echo -e "${RED}✗${NC} Agent modal may still have global setup steps"
        ((FAILED++))
    fi

    if grep -q "Get set up locally" frontend/app/page.tsx 2>/dev/null; then
        check "Hero has global 'Get set up' dialog"
    else
        echo -e "${RED}✗${NC} Hero missing global setup dialog"
        ((FAILED++))
    fi
else
    echo -e "${YELLOW}⚠${NC} frontend/ directory not found"
fi
echo ""

# 5. Frontend Agents Data
echo "5.  Frontend Agents Data"
echo "------------------------"
if [ -f "frontend/lib/agents.ts" ]; then
    for preset in "${PRESETS[@]}"; do
        if grep -q "id: \"${preset}\"" frontend/lib/agents.ts 2>/dev/null; then
            check "Frontend has agent data for ${preset}"
        else
            echo -e "${YELLOW}⚠${NC} Frontend missing agent data for ${preset}"
        fi
    done

    if grep -q "AGENT_PRESET=" frontend/lib/agents.ts 2>/dev/null; then
        check "Frontend install commands use AGENT_PRESET"
    else
        echo -e "${RED}✗${NC} Frontend install commands may not match Makefile pattern"
        ((FAILED++))
    fi
else
    echo -e "${RED}✗${NC} frontend/lib/agents.ts not found"
    ((FAILED++))
fi
echo ""

# 6. README
echo "6.  Documentation"
echo "------------------"
if [ -f "README.md" ]; then
    grep -q "port 4280" README.md 2>/dev/null; check "README mentions port 4280"
    grep -q "make install" README.md 2>/dev/null; check "README mentions make install"
    grep -q "make run" README.md 2>/dev/null; check "README mentions make run"
    grep -q "make docker-up" README.md 2>/dev/null; check "README mentions make docker-up"
else
    echo -e "${RED}✗${NC} README.md not found"
    ((FAILED++))
fi
echo ""

# 7. Docker Compose
echo "7.  Docker Configuration"
echo "------------------------"
if [ -f "docker-compose.yml" ]; then
    grep -q "4280" docker-compose.yml 2>/dev/null; check "docker-compose.yml uses port 4280"
    grep -q "AGENT_PRESET" docker-compose.yml 2>/dev/null; check "docker-compose.yml uses AGENT_PRESET"
else
    echo -e "${YELLOW}⚠${NC} docker-compose.yml not found"
fi
echo ""

# Summary
echo "======================"
echo "TEST SUMMARY"
echo "======================"
echo -e "${GREEN}Passed: ${PASSED}${NC}"
if [ $FAILED -gt 0 ]; then
    echo -e "${RED}Failed: ${FAILED}${NC}"
    exit 1
else
    echo -e "${GREEN}Failed: ${FAILED}${NC}"
    echo ""
    echo -e "${GREEN}All checks passed!${NC}"
    exit 0
fi
