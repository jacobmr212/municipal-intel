-- Assessment Platform Tables Migration
-- Creates tables for the ERP Assessment feature

-- Assessment table (main assessment record)
CREATE TABLE IF NOT EXISTS "Assessment" (
    id TEXT PRIMARY KEY,
    "userId" TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft',
    "organizationProfile" JSONB,
    "createdAt" TIMESTAMP NOT NULL DEFAULT NOW(),
    "updatedAt" TIMESTAMP NOT NULL DEFAULT NOW(),

    -- Foreign key to users table
    CONSTRAINT fk_user FOREIGN KEY ("userId") REFERENCES users(id) ON DELETE CASCADE
);

-- AssessmentSection table (stores answers for each section)
CREATE TABLE IF NOT EXISTS "AssessmentSection" (
    id TEXT PRIMARY KEY,
    "assessmentId" TEXT NOT NULL,
    "sectionNumber" TEXT NOT NULL,
    answers JSONB NOT NULL DEFAULT '{}',
    "aiFindings" JSONB,
    status TEXT NOT NULL DEFAULT 'not-started',
    "createdAt" TIMESTAMP NOT NULL DEFAULT NOW(),
    "updatedAt" TIMESTAMP NOT NULL DEFAULT NOW(),

    -- Foreign key to Assessment table
    CONSTRAINT fk_assessment FOREIGN KEY ("assessmentId") REFERENCES "Assessment"(id) ON DELETE CASCADE,

    -- Unique constraint: one record per assessment per section
    CONSTRAINT unique_assessment_section UNIQUE ("assessmentId", "sectionNumber")
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_assessment_user ON "Assessment"("userId");
CREATE INDEX IF NOT EXISTS idx_assessment_status ON "Assessment"(status);
CREATE INDEX IF NOT EXISTS idx_section_assessment ON "AssessmentSection"("assessmentId");
CREATE INDEX IF NOT EXISTS idx_section_status ON "AssessmentSection"(status);

-- Add comments
COMMENT ON TABLE "Assessment" IS 'Main assessment records for ERP readiness evaluation';
COMMENT ON TABLE "AssessmentSection" IS 'Individual section responses within an assessment';
COMMENT ON COLUMN "Assessment"."organizationProfile" IS 'JSON object with state, entity type, population, etc from Section 1';
COMMENT ON COLUMN "AssessmentSection".answers IS 'JSON object with all question/answer pairs for this section';
COMMENT ON COLUMN "AssessmentSection"."aiFindings" IS 'JSON object with AI-generated analysis and recommendations';
