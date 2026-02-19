# Assessment Platform Porting Progress

**Date:** February 19, 2026
**From:** Next.js `/Users/jacob/Desktop/govtech-erp-platform`
**To:** FastAPI `/Users/jacob/Desktop/municipal-intel-temp`

## Current State

### ✅ What's Been Ported

1. **Basic Assessment Infrastructure**
   - `templates/assessment.html` - Conversational UI template
   - Routes: `/assessment/{id}`, `/assessment/{id}/section/{number}`
   - API endpoints: Create, list, get, save section
   - Database integration (same PostgreSQL as Scanner)

2. **Section 1 Prototype (4 questions)**
   - State selection
   - Entity type (city, county, town, village)
   - Population
   - Organization name
   - Auto-save functionality
   - Progress bar
   - Returns to dashboard on complete

3. **State Retirement Systems Data**
   - ✅ All 50 states ported to `/data/retirement_systems.json`
   - Ready to integrate into Section 1 expanded version

### 🚧 What Still Needs Porting

#### **Section 1: Full Organization Profile (9 more questions)**

From the Next.js version (`ConversationalSection1.tsx` - 1,400+ lines):

**Questions to port:**
5. Retirement system (state-specific options from retirement_systems.json)
6. Fiscal year start month
7. Fiscal year start day
8. Number of departments
9. Union presence (yes/no)
10. Union groups (chip builder - dynamic list)
11. Number of tax jurisdictions
12. Current ERP system
13. Number of employees

**Complex UI components to port:**
- **Retirement System Selector** - Dynamic dropdown based on selected state
- **Fiscal Year Selector** - Month dropdown + day dropdown (1-31)
- **Union Groups Chip Builder** - Add/remove chips dynamically
- **Summary Review Card** - Shows all answers with inline edit buttons
- **State-specific contextual responses** - Different AI messages per state

**Implementation notes:**
- Next.js version uses React state management with `useState`
- FastAPI version needs vanilla JS state machine
- Message flow must handle branching logic (skip union groups if no unions)
- Review card must allow editing any field and regenerate subsequent questions

#### **Section 3A: Pay Code Inventory**

From the Next.js version (`ConversationalSection3A.tsx` - 2,100+ lines):

**Features to port:**
- Category selection (Overtime, Shift Differential, Premium Pay, etc.)
- Pay structure questions per category
- Employee group discovery
- Pay code detail collection:
  - GL account mapping
  - Tax treatment (taxable/non-taxable)
  - Calculation method (flat rate, percentage, hours-based)
- Three-layer guidance system:
  1. Category-level context
  2. Pay code builder with inline questions
  3. Real-time compliance hints

**Complex logic:**
- Dynamic question flow based on category
- Multiple pay codes per category
- "Add Another" functionality
- Summary review with edit capability

**Optional feature (not yet implemented in Next.js):**
- Paste-and-triage flow (AI triages pasted pay code list into categories)

#### **Data Import System**

From `/app/assessment/[id]/import/page.tsx`:

**Import groups:**

**Group 1 - Payroll Data:**
- Earnings Codes
- Deduction Codes
- Tax Codes
- Employee Groups

**Group 2 - Financial Structure:**
- Funds
- Departments
- Chart of Accounts

**Features:**
- Paste/upload capability
- CSV/text parsing
- Progress tracking (X/4 imported, Y/3 imported)
- Dashboard integration showing import summary

#### **AI Integration**

From `/lib/ai/client.ts`:

**Features:**
- Anthropic Claude API integration (claude-sonnet-4-5-20250929)
- Real-time answer analysis
- Compliance findings generation
- State-specific rule validation
- Downstream impact analysis

**Implementation:**
- API calls during questionnaire flow
- AI findings stored in AssessmentSection.aiFindings
- Final report generation with all findings aggregated

#### **Assessment Dashboard**

From `/app/assessment/[id]/page.tsx`:

**Features to port:**
- Section cards with progress indicators
- Lock/unlock logic (Section 3 requires Section 1 complete)
- Overall progress bar
- Import summary display
- "Notify me" buttons for locked sections (tracks interest)

## Architecture Differences

### Next.js Version
- **Frontend:** React components with TypeScript
- **State Management:** React hooks (`useState`, `useEffect`)
- **Styling:** Tailwind CSS
- **API:** Next.js API routes
- **Database:** Prisma ORM

### FastAPI Version
- **Frontend:** Jinja2 templates with vanilla JavaScript
- **State Management:** Plain JS objects and message arrays
- **Styling:** Inline styles in template
- **API:** FastAPI routes
- **Database:** Raw SQL via SQLAlchemy (no ORM models)

## Estimated Effort

Based on code complexity:

| Component | Lines of Code | Estimated Time |
|-----------|---------------|----------------|
| Section 1 Full (9 questions) | ~800 JS lines | 4-6 hours |
| Retirement system integration | ~100 lines | 1 hour |
| Fiscal year selector | ~50 lines | 30 min |
| Union groups chip builder | ~150 lines | 2 hours |
| Summary review card | ~200 lines | 2-3 hours |
| Section 3A full | ~1,500 lines | 8-12 hours |
| Data import system | ~400 lines | 4-6 hours |
| AI integration | ~200 lines | 2-3 hours |
| Assessment dashboard | ~300 lines | 3-4 hours |
| **TOTAL** | **~3,700 lines** | **26-37 hours** |

This is a **multi-session project**. Recommended approach:

1. ✅ **Session 1 (Complete):** Basic infrastructure + Section 1 prototype
2. **Session 2:** Full Section 1 with all 13 questions
3. **Session 3:** Section 3A part 1 (category selection + pay structure)
4. **Session 4:** Section 3A part 2 (pay code details + summary)
5. **Session 5:** Data import system
6. **Session 6:** AI integration + assessment dashboard
7. **Session 7:** Testing + polish

## Alternative Approach

**Instead of porting everything**, consider:

### Option A: Hybrid Architecture
- Keep Scanner in FastAPI (already deployed, working great)
- Deploy Assessment platform separately as Next.js app
- Both share same PostgreSQL database
- Different subdomains or URL paths

**Pros:**
- Next.js version already fully built (3,500+ lines)
- No porting effort needed
- Can iterate on each independently
- Easier to maintain

**Cons:**
- Two separate deployments
- Two codebases to maintain

### Option B: Continue Porting (Current Path)
- Port everything to FastAPI
- Unified codebase
- Single deployment

**Pros:**
- One tech stack
- Easier for you to manage long-term
- Single admin panel for everything

**Cons:**
- 26-37 hours of development work
- Need to recreate complex React components in vanilla JS
- Risk of bugs during translation

## Next Session Tasks

If continuing with porting (Option B):

1. **Expand Section 1 to include retirement system question**
   - Load retirement_systems.json
   - Show state-specific options based on user's selected state
   - Add contextual AI response for selected system

2. **Add fiscal year questions**
   - Month dropdown (January-December)
   - Day dropdown (1-31, dynamic based on month)

3. **Add employee-related questions**
   - Department count
   - Employee count
   - Current ERP system

4. **Add union detection + groups**
   - Yes/No for union presence
   - If yes, chip builder for union group names
   - Skip if no

5. **Build summary review card**
   - Display all 13 answers
   - Inline edit buttons
   - Re-generate questions if edited

## Files Modified This Session

```
/Users/jacob/Desktop/municipal-intel-temp/
├── templates/
│   └── assessment.html          (NEW - 310 lines)
├── main.py                       (MODIFIED - added assessment routes + Section 1 script)
├── templates/app.html            (MODIFIED - wired up Start Assessment button)
├── data/
│   └── retirement_systems.json   (NEW - all 50 states)
└── ASSESSMENT_PORT_PROGRESS.md   (NEW - this file)
```

## Recommendation

**My recommendation: Option A (Hybrid Architecture)**

**Why:**
- The Next.js assessment platform is already sophisticated and battle-tested
- 3,500+ lines of working code vs 26-37 hours of porting
- Both can share the same database (already configured)
- You can have the best of both worlds:
  - FastAPI for Scanner (lightweight, fast, Python-based)
  - Next.js for Assessment (rich UI, TypeScript, React)

**How to implement:**
1. Deploy Next.js app to Vercel (takes 10 minutes)
2. Point both to same Neon PostgreSQL database
3. Add link in FastAPI admin panel to Assessment platform
4. Users can access both from same login

**If you still want Option B (full port):**
- We've built the foundation this session
- We'll continue in next session with full Section 1
- Plan for 6-7 more sessions to complete everything

What would you like to do?
